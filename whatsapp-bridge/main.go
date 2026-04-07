package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	_ "github.com/mattn/go-sqlite3"
	"github.com/mdp/qrterminal/v3"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"
)

var (
	waClient      *whatsmeow.Client
	botName       string
	webhookURL    string
	currentQRCode string // último código QR recibido
)

// IncomingMessage is sent to the bot service when a WhatsApp message is received.
type IncomingMessage struct {
	Chat       string `json:"chat"`
	Sender     string `json:"sender"`
	SenderName string `json:"sender_name"`
	Message    string `json:"message"`
	MessageID  string `json:"message_id"`
	IsGroup    bool   `json:"is_group"`
	Timestamp  int64  `json:"timestamp"`
}

// SendRequest is received from the bot service to send a WhatsApp message.
type SendRequest struct {
	Chat    string `json:"chat"`
	Message string `json:"message"`
}

func getMessageText(msg *waE2E.Message) string {
	if msg == nil {
		return ""
	}
	if msg.GetConversation() != "" {
		return msg.GetConversation()
	}
	if ext := msg.GetExtendedTextMessage(); ext != nil {
		return ext.GetText()
	}
	return ""
}

func shouldRespond(text string, mentioned bool) bool {
	if mentioned {
		return true
	}
	lower := strings.ToLower(strings.TrimSpace(text))
	trigger := strings.ToLower(botName)
	return strings.HasPrefix(lower, trigger) || strings.Contains(lower, "@"+trigger)
}

func eventHandler(evt interface{}) {
	switch v := evt.(type) {
	case *events.Message:
		// Ignore own messages
		if v.Info.IsFromMe {
			return
		}

		text := getMessageText(v.Message)
		if text == "" {
			return
		}

		isGroup := v.Info.Chat.Server == types.GroupServer

		// Check if bot is mentioned via WhatsApp @mention
		mentioned := false
		if waClient.Store.ID != nil {
			myUser := waClient.Store.ID.User
			if ext := v.Message.GetExtendedTextMessage(); ext != nil {
				if ci := ext.GetContextInfo(); ci != nil {
					for _, jid := range ci.GetMentionedJID() {
						if strings.Contains(jid, myUser) {
							mentioned = true
							break
						}
					}
				}
			}
		}

		// In groups, only respond when mentioned or trigger word used
		if isGroup && !shouldRespond(text, mentioned) {
			return
		}

		incoming := IncomingMessage{
			Chat:       v.Info.Chat.String(),
			Sender:     v.Info.Sender.String(),
			SenderName: v.Info.PushName,
			Message:    text,
			MessageID:  v.Info.ID,
			IsGroup:    isGroup,
			Timestamp:  v.Info.Timestamp.Unix(),
		}

		go forwardToBot(incoming)
	}
}

func forwardToBot(msg IncomingMessage) {
	jsonData, err := json.Marshal(msg)
	if err != nil {
		log.Printf("[bridge] error marshaling message: %v", err)
		return
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(webhookURL, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		log.Printf("[bridge] error forwarding to bot: %v", err)
		return
	}
	resp.Body.Close()
	log.Printf("[bridge] forwarded message from %s in %s", msg.SenderName, msg.Chat)
}

func sendWhatsAppMessage(req SendRequest) error {
	jid, err := types.ParseJID(req.Chat)
	if err != nil {
		return fmt.Errorf("invalid JID %q: %w", req.Chat, err)
	}

	msg := &waE2E.Message{
		Conversation: proto.String(req.Message),
	}

	_, err = waClient.SendMessage(context.Background(), jid, msg)
	return err
}

func handleSend(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req SendRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}

	if err := sendWhatsAppMessage(req); err != nil {
		log.Printf("[bridge] error sending message: %v", err)
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	log.Printf("[bridge] sent message to %s", req.Chat)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "sent"})
}

func handleQR(w http.ResponseWriter, r *http.Request) {
	if waClient != nil && waClient.IsConnected() {
		w.Header().Set("Content-Type", "text/html")
		fmt.Fprint(w, `<html><body style="font-family:Arial;text-align:center;padding:50px">
			<h2>WhatsApp ya esta conectado</h2></body></html>`)
		return
	}
	if currentQRCode == "" {
		w.Header().Set("Content-Type", "text/html")
		fmt.Fprint(w, `<html><body style="font-family:Arial;text-align:center;padding:50px">
			<h2>Esperando QR...</h2><p>Recarga la pagina en unos segundos.</p>
			<script>setTimeout(()=>location.reload(), 3000)</script></body></html>`)
		return
	}
	w.Header().Set("Content-Type", "text/html")
	fmt.Fprintf(w, `<html><head>
		<script src="https://cdn.jsdelivr.net/npm/qrcodejs/qrcode.min.js"></script>
		<style>body{font-family:Arial;text-align:center;padding:50px}
		#qr{display:inline-block;margin:20px}</style>
	</head><body>
		<h2>Escaneá este QR con WhatsApp</h2>
		<p>WhatsApp > Dispositivos vinculados > Vincular dispositivo</p>
		<div id="qr"></div>
		<p><small>Se actualiza cada 5 segundos automaticamente</small></p>
		<script>
			new QRCode(document.getElementById("qr"), {
				text: %q,
				width: 300,
				height: 300
			});
			setTimeout(()=>location.reload(), 5000);
		</script>
	</body></html>`, currentQRCode)
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	connected := waClient != nil && waClient.IsConnected()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"connected": connected,
		"timestamp": time.Now().Unix(),
	})
}

func main() {
	botName = os.Getenv("BOT_NAME")
	if botName == "" {
		botName = "Bot"
	}

	webhookURL = os.Getenv("BOT_WEBHOOK_URL")
	if webhookURL == "" {
		webhookURL = "http://bot:8000/webhook"
	}

	listenAddr := os.Getenv("LISTEN_ADDR")
	if listenAddr == "" {
		listenAddr = ":8080"
	}

	// Initialize WhatsApp session store
	dbLog := waLog.Stdout("DB", "WARN", true)
	container, err := sqlstore.New(context.Background(), "sqlite3", "file:/data/whatsapp.db?_foreign_keys=on", dbLog)
	if err != nil {
		log.Fatalf("Failed to init DB: %v", err)
	}

	deviceStore, err := container.GetFirstDevice(context.Background())
	if err != nil {
		log.Fatalf("Failed to get device: %v", err)
	}

	clientLog := waLog.Stdout("WA", "WARN", true)
	waClient = whatsmeow.NewClient(deviceStore, clientLog)
	waClient.AddEventHandler(eventHandler)

	// Connect — show QR if first time
	if waClient.Store.ID == nil {
		qrChan, _ := waClient.GetQRChannel(context.Background())
		if err := waClient.Connect(); err != nil {
			log.Fatalf("Failed to connect: %v", err)
		}
		scanned := false
		for evt := range qrChan {
			if evt.Event == "code" {
				currentQRCode = evt.Code
				fmt.Println("\n========== ESCANEA ESTE QR CON WHATSAPP ==========")
				qrterminal.GenerateHalfBlock(evt.Code, qrterminal.L, os.Stdout)
				fmt.Println("===================================================")
				fmt.Printf("\nO abrí en el navegador: https://efficient-spirit-production.up.railway.app/qr\n\n")
			} else if evt.Event == "success" {
				scanned = true
				log.Println("[bridge] QR escaneado exitosamente!")
			} else {
				log.Printf("[bridge] QR event: %s", evt.Event)
			}
		}
		// Si el canal se cerró sin escanear, reiniciar para generar nuevo QR
		if !scanned {
			log.Println("[bridge] QR expiró sin escanear, reiniciando...")
			os.Exit(1)
		}
	} else {
		if err := waClient.Connect(); err != nil {
			log.Fatalf("Failed to connect: %v", err)
		}
	}

	log.Println("[bridge] WhatsApp connected!")

	// HTTP server for bot communication
	mux := http.NewServeMux()
	mux.HandleFunc("/send", handleSend)
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/qr", handleQR)

	server := &http.Server{
		Addr:         listenAddr,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
	}

	go func() {
		log.Printf("[bridge] HTTP server on %s", listenAddr)
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	// Graceful shutdown
	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c

	log.Println("[bridge] shutting down...")
	waClient.Disconnect()
	server.Shutdown(context.Background())
}

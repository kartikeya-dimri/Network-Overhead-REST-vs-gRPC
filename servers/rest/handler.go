package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"time"
)

// EchoResponse wraps the echoed payload with server-side timing.
type EchoResponse struct {
	Payload  interface{} `json:"payload"`
	ServerNs int64       `json:"server_ns"` // deser + ser time on server (nanoseconds)
}

// echoHandler reads the JSON body, deserializes it, re-serializes it,
// and echoes it back. Reports server-side ser/deser timing both in
// the response body (server_ns field) and the X-Server-Ns header.
func echoHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}

	// --- deserialization ---
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "read error", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	t0 := time.Now()
	var payload interface{}
	if err := json.Unmarshal(body, &payload); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}
	t1 := time.Now()
	deserNs := t1.Sub(t0).Nanoseconds()

	// --- build response ---
	resp := EchoResponse{
		Payload: payload,
	}

	// --- serialization ---
	t2 := time.Now()
	out, err := json.Marshal(resp)
	if err != nil {
		http.Error(w, "marshal error", http.StatusInternalServerError)
		return
	}
	t3 := time.Now()
	serNs := t3.Sub(t2).Nanoseconds()

	serverNs := deserNs + serNs

	// Re-marshal with the actual timing value set
	resp.ServerNs = serverNs
	out, err = json.Marshal(resp)
	if err != nil {
		http.Error(w, "marshal error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Content-Length", strconv.Itoa(len(out)))
	w.Header().Set("X-Server-Ns", fmt.Sprintf("%d", serverNs))
	w.WriteHeader(http.StatusOK)
	w.Write(out)
}

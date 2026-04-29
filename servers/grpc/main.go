package main

import (
	"fmt"
	"log"
	"net"
	"os"

	pb "github.com/kartikeya-dimri/network-overhead/servers/grpc/proto"
	"google.golang.org/grpc"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "50051"
	}

	addr := fmt.Sprintf(":%s", port)
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	srv := grpc.NewServer()
	pb.RegisterEchoServiceServer(srv, &echoServer{})

	log.Printf("gRPC echo server listening on %s", addr)
	if err := srv.Serve(lis); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}

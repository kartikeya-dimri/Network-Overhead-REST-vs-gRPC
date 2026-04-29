package main

import (
	"context"
	"time"

	pb "github.com/kartikeya-dimri/network-overhead/servers/grpc/proto"
	"google.golang.org/protobuf/proto"
)

type echoServer struct {
	pb.UnimplementedEchoServiceServer
}

// Echo measures protobuf deserialization and serialization cost on the server.
//
// The gRPC framework deserializes the request before this handler is called
// and serializes the response after it returns, so we cannot instrument those
// directly. Instead we re-perform the same operations with identical data
// and time them. At concurrency=1 with warm caches this is representative.
func (s *echoServer) Echo(ctx context.Context, req *pb.EchoRequest) (*pb.EchoResponse, error) {
	// --- measure deserialization ---
	// Marshal the already-decoded request back to bytes, then time Unmarshal.
	rawReq, err := proto.Marshal(req)
	if err != nil {
		return nil, err
	}

	t0 := time.Now()
	var reqCopy pb.EchoRequest
	if err := proto.Unmarshal(rawReq, &reqCopy); err != nil {
		return nil, err
	}
	deserNs := time.Since(t0).Nanoseconds()

	// --- build response ---
	resp := &pb.EchoResponse{
		Payload: req.Payload,
	}

	// --- measure serialization ---
	t1 := time.Now()
	if _, err := proto.Marshal(resp); err != nil {
		return nil, err
	}
	serNs := time.Since(t1).Nanoseconds()

	resp.ServerNs = deserNs + serNs
	return resp, nil
}

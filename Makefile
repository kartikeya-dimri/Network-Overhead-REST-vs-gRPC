# Makefile — REST vs gRPC Network Overhead
#
# Targets:
#   make proto       — regenerate Go stubs from echo.proto
#   make build       — build both server binaries
#   make clean       — remove built binaries
#   make aggregate   — run post-processing pipeline
#   make plots       — generate all plots

PROTO_DIR   = servers/grpc/proto
PROTO_FILE  = $(PROTO_DIR)/echo.proto

REST_SRC    = ./servers/rest/
GRPC_SRC    = ./servers/grpc/

# ---- protobuf code generation ----
# Prerequisites:
#   go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
#   go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
#   brew install protobuf   (or apt install protobuf-compiler)
.PHONY: proto
proto:
	protoc \
		--go_out=. --go_opt=paths=source_relative \
		--go-grpc_out=. --go-grpc_opt=paths=source_relative \
		$(PROTO_FILE)
	@echo "[proto] generated $(PROTO_DIR)/echo.pb.go and echo_grpc.pb.go"

# ---- build ----
.PHONY: build build-rest build-grpc
build: build-rest build-grpc

build-rest:
	go build -o rest-server $(REST_SRC)
	@echo "[build] rest-server"

build-grpc:
	go build -o grpc-server $(GRPC_SRC)
	@echo "[build] grpc-server"

# ---- analysis ----
.PHONY: aggregate plots
aggregate:
	python3 analysis/aggregate.py

plots:
	python3 analysis/plot_space.py
	python3 analysis/plot_time.py

# ---- clean ----
.PHONY: clean
clean:
	rm -f rest-server grpc-server

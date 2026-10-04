package main

import (
	"os"

	"github.com/Flow-Research/workstream/cli/internal/command"
)

var version = "dev"

func main() {
	os.Exit(command.Run(os.Args[1:], os.Stdout, os.Stderr, os.Getenv, version))
}

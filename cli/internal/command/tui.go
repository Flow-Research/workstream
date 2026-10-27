package command

import (
	"context"
	"io"
	"os"
	"strings"
	"sync"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/Flow-Research/workstream/cli/internal/tui"
	"github.com/charmbracelet/x/term"
	"github.com/spf13/cobra"
)

func addTUI(root *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer, getenv environment) {
	var plain bool
	cmd := &cobra.Command{Use: "tui", Short: "Open the opt-in contributor workbench", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if *output != "text" {
				return commandError{"invalid_output", "tui requires text output; use ordinary commands with --output json"}
			}
			input, ok := cmd.InOrStdin().(*os.File)
			out, outputFile := stdout.(*os.File)
			if !ok || !outputFile || !term.IsTerminal(input.Fd()) || !term.IsTerminal(out.Fd()) {
				return commandError{"interactive_terminal_required", "tui requires interactive stdin and stdout; use workstream --help and ordinary commands with --output json"}
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			return runTUI(cmd.Context(), apiClient, input, stdout, getenv, plain)
		}}
	cmd.Flags().BoolVar(&plain, "plain", false, "Use a plain single-column view without alternate screen or color")
	root.AddCommand(cmd)
}

func runTUI(ctx context.Context, client tui.Client, input io.Reader, output io.Writer, getenv environment, plain bool) (err error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	observed := &terminalOutput{destination: output, cancel: cancel}
	var terminalWriter io.Writer = observed
	if file, ok := output.(term.File); ok {
		terminalWriter = terminalFileOutput{terminalOutput: observed, File: file}
	}
	noColor := plain || getenv("NO_COLOR") != ""
	model := tui.New(ctx, client, getenv("WORKSTREAM_TOKEN"), plain, noColor)
	defer model.Close()
	// Only terminal capabilities reach the renderer, never the bearer environment.
	env := []string{}
	for _, name := range []string{"TERM", "COLORTERM", "TERM_PROGRAM"} {
		value := getenv(name)
		if len(value) > 64 || strings.IndexFunc(value, func(r rune) bool {
			return !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || strings.ContainsRune("_.+-", r))
		}) >= 0 {
			continue
		}
		if value != "" {
			env = append(env, name+"="+value)
		}
	}
	if noColor {
		env = append(env, "NO_COLOR=1")
	}
	program := tea.NewProgram(model, tea.WithContext(ctx), tea.WithInput(input), tea.WithOutput(terminalWriter), tea.WithEnvironment(env), tea.WithoutCatchPanics())
	err = runTerminalProgram(program)
	// Bubble Tea discards renderer flush errors, including errors during close.
	// A broken output must still produce an observable failure, not exit zero.
	if observed.failed() {
		return &api.Failure{Code: "terminal_unavailable"}
	}
	return err
}

// Keep the terminal lifecycle separate from error presentation. This narrow
// boundary also covers initialization failure after the input entered raw mode.
type terminalProgram interface {
	Run() (tea.Model, error)
	Kill()
}

func runTerminalProgram(program terminalProgram) (err error) {
	defer func() {
		program.Kill()
		if recover() != nil {
			err = &api.Failure{Code: "terminal_unavailable"}
		}
	}()
	if _, err := program.Run(); err != nil {
		return &api.Failure{Code: "terminal_unavailable"}
	}
	return nil
}

// terminalOutput cancels on the first write error without retaining raw errors.
// Subsequent cleanup writes are still attempted if the channel recovers.
type terminalOutput struct {
	destination io.Writer
	cancel      context.CancelFunc
	mu          sync.Mutex
	broken      bool
}

func (w *terminalOutput) Write(value []byte) (int, error) {
	w.mu.Lock()
	n, err := w.destination.Write(value)
	if err == nil && n != len(value) {
		err = io.ErrShortWrite
	}
	if err != nil {
		w.broken = true
	}
	w.mu.Unlock()
	if err != nil {
		w.cancel()
	}
	return n, err
}

func (w *terminalOutput) failed() bool { w.mu.Lock(); defer w.mu.Unlock(); return w.broken }

// Preserve real terminal descriptor detection while observing output writes.
type terminalFileOutput struct {
	*terminalOutput
	term.File
}

func (w terminalFileOutput) Write(value []byte) (int, error) { return w.terminalOutput.Write(value) }

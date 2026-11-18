package login

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os/exec"
	"runtime"
	"sync"
	"time"

	"github.com/zalando/go-keyring"
	"golang.org/x/oauth2"
)

// OpenBrowser launches the operating system browser without a shell.
func OpenBrowser(address string) error {
	var command *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		command = exec.Command("open", address)
	case "windows":
		command = exec.Command("rundll32", "url.dll,FileProtocolHandler", address)
	default:
		command = exec.Command("xdg-open", address)
	}
	if err := command.Start(); err != nil {
		return errors.New("cannot open browser; open the displayed sign-in URL")
	}
	go func() { _ = command.Wait() }()
	return nil
}

func callback(state string, result chan<- string) http.Handler {
	var once sync.Once
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Referrer-Policy", "no-referrer")
		if r.Method != http.MethodGet || r.Host != "127.0.0.1:17843" || r.URL.Path != "/callback" {
			http.Error(w, "Invalid login callback", 400)
			return
		}
		q, err := url.ParseQuery(r.URL.RawQuery)
		if err != nil || len(q["state"]) != 1 || subtle.ConstantTimeCompare([]byte(q.Get("state")), []byte(state)) != 1 {
			http.Error(w, "Login was not completed; return to your terminal", 400)
			return
		}
		if q.Has("error") {
			if len(q["error"]) != 1 || q.Has("code") {
				http.Error(w, "Invalid login callback", 400)
				return
			}
			once.Do(func() { result <- "" })
			http.Error(w, "Login was declined. Return to your terminal.", 400)
			return
		}
		if len(q["code"]) != 1 || q.Get("code") == "" || len(q.Get("code")) > 8192 {
			http.Error(w, "Invalid login callback", 400)
			return
		}
		once.Do(func() { result <- q.Get("code") })
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		fmt.Fprintln(w, "Login received. Return to your terminal to confirm completion.")
	})
}

// Login performs browser code/PKCE login and stores only validated API credentials.
func (c *Client) Login(ctx context.Context, store Store, issuerURL, apiURL string, output io.Writer, launch func(string) error) error {
	apiOrigin, err := origin(apiURL)
	if err != nil {
		return err
	}
	return store.locked(func() error {
		if _, err := keyring.Get(secretService, secretAccount); err != nil && !errors.Is(err, keyring.ErrNotFound) {
			return errors.New("cannot access the OS credential store; unlock your desktop keychain before signing in")
		}
		p, config, err := c.provider(ctx, issuerURL)
		if err != nil {
			return err
		}
		state := randomValue()
		verifier := oauth2.GenerateVerifier()
		result := make(chan string, 1)
		listener, err := net.Listen("tcp4", "127.0.0.1:17843")
		if err != nil {
			return errors.New("login callback port is busy; finish the other login first")
		}
		server := &http.Server{Handler: callback(state, result), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 5 * time.Second, WriteTimeout: 5 * time.Second, MaxHeaderBytes: 8192}
		defer server.Close()
		go func() { _ = server.Serve(listener) }()
		address := config.AuthCodeURL(state, oauth2.S256ChallengeOption(verifier))
		fmt.Fprintln(output, "Sign in using your browser:", address)
		if err := launch(address); err != nil {
			fmt.Fprintln(output, "Browser could not open automatically; open that URL on this computer.")
		}
		timeout := time.NewTimer(5 * time.Minute)
		defer timeout.Stop()
		var code string
		select {
		case code = <-result:
		case <-ctx.Done():
			return errors.New("login cancelled")
		case <-timeout.C:
			return errors.New("login timed out; run workstream login again")
		}
		if code == "" {
			return errors.New("sign-in was declined; no credential was saved")
		}
		token, err := config.Exchange(context.WithValue(ctx, oauth2.HTTPClient, c.HTTP), code, oauth2.VerifierOption(verifier))
		if err != nil {
			return errors.New("identity rejected the authorization code; run workstream login again")
		}
		subject, err := c.verify(ctx, p, token, "")
		if err != nil {
			return err
		}
		if err = store.save(&Session{Issuer: issuerURL, APIOrigin: apiOrigin, Subject: subject, Token: token}); err != nil {
			return err
		}
		fmt.Fprintln(output, "Signed in. You can now run workstream whoami.")
		return nil
	})
}

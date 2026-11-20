use std::env;
use std::process::Command;

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    // If first arg is "serve-p2p", bind a simple listener on the Tailscale IP.
    if args.first().map(|s| s.as_str()) == Some("serve-p2p") {
        let ip = args.get(1).cloned().unwrap_or_else(|| "100.91.36.108".to_string());
        let port = args.get(2).cloned().unwrap_or_else(|| "9000".to_string());
        println!("rho-tailscale p2p listener on {}:{}", ip, port);
        // Placeholder: real implementation would bind a TCP socket here.
        return;
    }
    // Otherwise wrap the native tailscale CLI.
    let status = Command::new("tailscale")
        .args(&args)
        .status()
        .expect("failed to invoke tailscale");
    std::process::exit(status.code().unwrap_or(1));
}

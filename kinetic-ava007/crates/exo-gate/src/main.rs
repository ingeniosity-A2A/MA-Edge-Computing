use clap::Parser;
use exo_gate::{full_check, route};

#[derive(Parser, Debug)]
#[command(name = "gate", about = "Exoskeleton capability gate")]
struct Cli {
    #[arg(long)]
    full_check: bool,
    #[arg(long)]
    route: Option<String>,
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();
    if cli.full_check {
        let results = full_check().await;
        for r in &results {
            println!("{}: {} ({})", r.name, if r.passed { "PASS" } else { "FAIL" }, r.detail);
        }
        let all = results.iter().all(|r| r.passed);
        std::process::exit(if all { 0 } else { 1 });
    }
    if let Some(input) = cli.route {
        println!("{}", route(&input));
    }
}

//! Explicit real-runsc qualification entrypoint for the generic trial backend.

#![allow(dead_code)]

#[path = "../trial_docker.rs"]
mod trial_docker;
#[path = "../trial_engine.rs"]
mod trial_engine;
#[path = "../trial_relay.rs"]
mod trial_relay;

#[allow(dead_code)]
#[path = "../../tests/trial_docker.rs"]
mod qualification;

fn main() {
    qualification::concrete_runtime_builds_and_runs_offline_under_runsc();
}

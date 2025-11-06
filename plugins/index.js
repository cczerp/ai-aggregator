// plugin-arbimgr/index.js
import fetch from "node-fetch";

export const actions = {
  async check_status() {
    const res = await fetch("http://localhost:5050/status");
    return await res.json();
  },

  async run_scan() {
    const res = await fetch("http://localhost:5050/scan", { method: "POST" });
    return await res.json();
  },

  async analyze_logs() {
    const res = await fetch("http://localhost:5050/logs");
    return await res.text();
  },

  async execute_trade(_, input) {
    const res = await fetch("http://localhost:5050/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input)
    });
    return await res.json();
  }
};

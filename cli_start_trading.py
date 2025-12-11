from ai_agent.driver import build_driver

if __name__ == "__main__":
    driver = build_driver(".")
    print("Starting AI-powered trading engine...")
    driver.start_trading("auto")

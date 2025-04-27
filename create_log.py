import os
import datetime

verbose = True
log_session = None



def create_log(message):
    global log_session
    if log_session is None:
        os.makedirs("log", exist_ok=True)
        session_log_path = f"log/{datetime.datetime.now().strftime('%Y-%m-%d')}_session.log"
        log_session = session_log_path
    with open(log_session, "a") as f:
        f.write(f"{datetime.datetime.now()}: {message}\n")

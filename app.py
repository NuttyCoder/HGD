# app.py
import time
import threading
import sqlite3
import datetime
import smtplib
from email.mime.text import MIMEText
import requests
import smbus
from influxdb import InfluxDBClient
from twilio.rest import Client
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# -------------------------------
# Global Variables and Constants
# -------------------------------
SLAVE_ADDR = 4                 # I²C address for the Arduino slave
I2C_BUS   = 1                 # Most Raspberry Pis use bus 1
global_sensor_data = {}        # Latest sensor reading dictionary
last_alert_time = 0            # For rate-limiting alerts (in seconds)
ALERT_RATE_LIMIT = 300         # 5 minutes


# -------------------------------
# I²C Sensor Reading Functions
# -------------------------------
def read_sensor_data():
    """
    Read raw data from the Uno over I²C.
    The sensor message is expected to be a string of up to 64 bytes.
    """
    try:
        bus = smbus.SMBus(I2C_BUS)
        num_bytes = 64
        data = bus.read_i2c_block_data(SLAVE_ADDR, 0, num_bytes)
        # Convert list of integers to string and remove trailing nulls
        sensor_string = ''.join(chr(x) for x in data).split('\x00')[0].strip()
        return sensor_string
    except Exception as e:
        print("I2C communication error:", e)
        return None


def parse_and_validate(sensor_string):
    """
    Parses the given sensor string with the expected format:
      "#T:xx.xx,P:xx.xx,E:xx.xx,W:xx.xx,S:x,CS:XX$"
    and validates it via checksum.
    Returns a dictionary with sensor readings if the parsing is successful.
    """
    if not sensor_string.startswith("#") or not sensor_string.endswith("$"):
        return None

    content = sensor_string[1:-1]  # remove the '#' and '$'
    parts = content.split(',')
    data = {}
    cs_from_msg = None
    message_for_checksum = ""

    for part in parts:
        if part.startswith("CS:"):
            cs_from_msg = part[3:]
        else:
            message_for_checksum += part + ","
    if message_for_checksum.endswith(","):
        message_for_checksum = message_for_checksum[:-1]

    # Calculate checksum (sum of ASCII codes modulo 256)
    checksum_calc = sum(ord(c) for c in message_for_checksum) % 256
    try:
        checksum_msg = int(cs_from_msg, 16)
    except Exception as e:
        print("Checksum conversion error:", e)
        return None
    if checksum_calc != checksum_msg:
        print("Checksum mismatch:", hex(checksum_calc), "vs", cs_from_msg)
        return None

    # Parse sensor values into dictionary:
    for part in parts:
        if part.startswith("T:"):
            data["temperature"] = float(part[2:])
        elif part.startswith("P:"):
            data["pH"] = float(part[2:])
        elif part.startswith("E:"):
            data["EC"] = float(part[2:])
        elif part.startswith("W:"):
            data["water_level"] = float(part[2:])
        elif part.startswith("S:"):
            data["status"] = int(part[2:])
    return data


# -------------------------------
# Data Logging Functions
# -------------------------------
def log_data(data):
    """Log sensor data to a SQLite database."""
    try:
        conn = sqlite3.connect("sensor_data.db")
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS sensor_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        temperature REAL,
                        pH REAL,
                        EC REAL,
                        water_level REAL,
                        status INTEGER
                    )''')
        c.execute("INSERT INTO sensor_data (temperature, pH, EC, water_level, status) VALUES (?, ?, ?, ?, ?)",
                  (data.get("temperature"), data.get("pH"), data.get("EC"), data.get("water_level"), data.get("status")))
        conn.commit()
        conn.close()
    except Exception as e:
        print("SQLite logging error:", e)


# Initialize InfluxDB client (make sure InfluxDB is running)
influx_client = InfluxDBClient(host='localhost', port=8086)
try:
    influx_client.switch_database('sensor_data')
except Exception as e:
    print("Error switching to InfluxDB database:", e)


def log_data_influxdb(data):
    """
    Log sensor data to InfluxDB.
    The measurement is named "sensors" with fields for each sensor reading.
    """
    json_body = [
        {
            "measurement": "sensors",
            "tags": {
                "host": "raspberry_pi",
                "sensor": "hydroponics"
            },
            "time": datetime.datetime.utcnow().isoformat(),
            "fields": {
                "temperature": float(data.get("temperature", 0)),
                "pH": float(data.get("pH", 0)),
                "EC": float(data.get("EC", 0)),
                "water_level": float(data.get("water_level", 0)),
                "status": int(data.get("status", 0))
            }
        }
    ]
    try:
        influx_client.write_points(json_body)
        print("InfluxDB logging successful.")
    except Exception as e:
        print("Error logging to InfluxDB:", e)


# -------------------------------
# Alerting Functions
# -------------------------------
def send_email_alert(data):
    """Send an email alert if a sensor error is detected."""
    sender = "your_email@example.com"
    recipient = "alert_recipient@example.com"
    subject = "Sensor Alert: Issue Detected"
    body = f"Alert! A sensor error has been detected:\n\n{data}"
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient

    try:
        smtp_server = 'smtp.example.com'  # Update with your SMTP server
        smtp_port = 587
        with smtplib.SMTP(smtp_server, smtp_port) as s:
            s.starttls()
            s.login("your_email_username", "your_email_password")
            s.sendmail(sender, [recipient], msg.as_string())
        print("Alert email sent.")
    except Exception as e:
        print("Failed to send email alert:", e)


def send_sms_alert(data):
    """Send an SMS alert via Twilio if a sensor error is detected."""
    account_sid = 'your_twilio_account_sid'
    auth_token = 'your_twilio_auth_token'
    client = Client(account_sid, auth_token)
    body = f"Sensor Alert: Error detected! Data: {data}"
    try:
        message = client.messages.create(
            body=body,
            from_='+1234567890',  # Your Twilio number
            to='+0987654321'      # Recipient's phone number
        )
        print("SMS alert sent. SID:", message.sid)
    except Exception as e:
        print("Failed to send SMS alert:", e)


def send_slack_alert(data):
    """Send a Slack alert via webhook if a sensor error is detected."""
    webhook_url = 'https://hooks.slack.com/services/your/slack/webhook'
    payload = {"text": f"Sensor Alert: Error detected!\nData: {data}"}
    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200:
            print("Slack alert sent successfully.")
        else:
            print("Slack alert failed, status code:", response.status_code)
    except Exception as e:
        print("Exception sending Slack alert:", e)


def send_push_notification(data):
    """Send a push notification via Pushover if a sensor error is detected."""
    url = "https://api.pushover.net/1/messages.json"
    payload = {
        "token": "your_pushover_app_token",
        "user": "your_pushover_user_key",
        "message": f"Sensor Alert: Error detected!\nData: {data}",
        "title": "Sensor Alert!"
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Push notification sent successfully.")
        else:
            print("Push notification failed, status code:", response.status_code)
    except Exception as e:
        print("Exception sending push notification:", e)


# -------------------------------
# Sensor Polling Thread
# -------------------------------
def sensor_polling_thread():
    global global_sensor_data, last_alert_time
    while True:
        sensor_str = read_sensor_data()
        if sensor_str:
            parsed = parse_and_validate(sensor_str)
            if parsed:
                global_sensor_data = parsed
                # Log data to SQLite and InfluxDB
                log_data(parsed)
                log_data_influxdb(parsed)

                # If an error is detected (non-zero status), send alerts (with rate-limiting)
                if parsed.get("status", 0) != 0:
                    current_time = time.time()
                    if current_time - last_alert_time > ALERT_RATE_LIMIT:
                        send_email_alert(parsed)
                        send_sms_alert(parsed)
                        send_slack_alert(parsed)
                        send_push_notification(parsed)
                        last_alert_time = current_time
        else:
            print("No sensor data received.")
        time.sleep(2)  # Poll every 2 seconds


# -------------------------------
# Flask Routes
# -------------------------------
@app.route('/')
def dashboard():
    """Render the live sensor dashboard."""
    return render_template("dashboard.html", sensor_data=global_sensor_data)


@app.route('/api/data')
def api_data():
    """Return the latest sensor data as JSON."""
    return jsonify(global_sensor_data)


@app.route('/api/history')
def api_history():
    """Return the most recent 100 sensor records from SQLite as JSON."""
    try:
        conn = sqlite3.connect("sensor_data.db")
        c = conn.cursor()
        c.execute("SELECT timestamp, temperature, pH, EC, water_level, status FROM sensor_data ORDER BY timestamp DESC LIMIT 100")
        rows = c.fetchall()
        conn.close()
        data = []
        for row in rows:
            rec = {
                "timestamp": row[0],
                "temperature": row[1],
                "pH": row[2],
                "EC": row[3],
                "water_level": row[4],
                "status": row[5]
            }
            data.append(rec)
        return jsonify(data)
    except Exception as e:
        print("Error retrieving historical data:", e)
        return jsonify([])


@app.route('/historical')
def historical_dashboard():
    """Render the historical sensor data dashboard (uses Chart.js)."""
    return render_template("historical.html")


# -------------------------------
# Main Entry Point
# -------------------------------
if __name__ == '__main__':
    # Start sensor polling in a background thread
    sensor_thread = threading.Thread(target=sensor_polling_thread, daemon=True)
    sensor_thread.start()
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)

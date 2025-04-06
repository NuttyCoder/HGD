# HGD


Home Garden Dashboard
The idea behind this project is to create a DASHBOARD FOR A HOME HYDROPONICS SYSTEM - Which is the problem we are solving for.

This solution ties together all the enhancements we discussed—from sensor polling on the Elegoo Uno R3 (acting as an I²C slave) and Raspberry Pi (as the master), through logging sensor data (both in SQLite and InfluxDB), to multi‑channel alerting (email, SMS via Twilio, Slack, and push notifications via Pushover) and real‑time dashboards using Flask. In addition, we’ve included a Dockerfile and a Docker Compose file so you can containerize your stack, and two HTML template files for dashboards (one live and one historical using Chart.js).
Remember:
• Update all placeholders (like email credentials, Twilio keys, Slack webhook URL, Pushover keys, etc.) with your actual configuration.
• Ensure your hardware wiring and I²C level‑shifting are configured correctly before deployment.

PROCESS.........................................................................................................................................................................

1. Python Application Code
See app.py
2. Create a file named 'Dockerfile on your project root:

# Dockerfile
FROM python:3.9-slim

WORKDIR /app

Copy requirements file and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

Copy the rest of the application code
COPY . .

Expose the port that Flask will run on
EXPOSE 5000

Set environment variables required by Flask
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

Run the Flask application
CMD ["python", "app.py"]   

A sample requirements.txt might include:
Flask
smbus
influxdb
twilio
requests

3. Docker Compose File
# See file docker-compose.yml

4. HTML Templates
Place these files in a subfolder named 'templates'.
This template creates a live dashboard that polls the lastes sensor reading every 2 seconds.
# See templates/dashboard.html

4.1 templates/historical.html # See historical.html
This template uses Chart.js (loaded via a CDN) to display historical temperature trends. You can add additional charts similarly.

Docker & AWS Deployment:
Use the provided  and  to build and test your containers locally.
• Follow the AWS ECS/ECR instructions (or use your chosen IaC method like CloudFormation/CDK) to deploy this containerized solution to AWS Fargate.
Configuration:
• Ensure to update any placeholder credentials and configuration values before production deployment.
• Test the I²C communication between the Raspberry Pi and your Arduino (Elegoo Uno R3).

This creates a robust monitoring system built for high performance, advanced visualization, and multi‑channel alerting—all ready to be deployed, 
whether locally or in the cloud on AWS.

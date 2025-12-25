#!/bin/bash
# SSL Setup with Let's Encrypt (for Docker setup)

# Stop Docker containers to free port 80
cd /var/www/one9founders/backend
docker compose down

# Install certbot
sudo apt update
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d api.one9founders.com

# Restart Docker containers
docker compose up -d

# Auto-renewal
echo "0 12 * * * cd /var/www/one9founders/backend && docker compose down && /usr/bin/certbot renew --quiet && docker compose up -d" | sudo crontab -

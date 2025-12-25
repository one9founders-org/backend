#!/bin/bash
# SSL Setup with Let's Encrypt

# Install certbot
sudo apt update
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d api.one9founders.com

# Auto-renewal
sudo crontab -l | { cat; echo "0 12 * * * /usr/bin/certbot renew --quiet"; } | sudo crontab -

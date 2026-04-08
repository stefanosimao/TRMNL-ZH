# AWS Infrastructure & Server Management: TRMNL-ZH

This guide contains everything you need to manage, update, and troubleshoot your TRMNL-ZH server on AWS EC2.

---

## 1. Server Details

- **Public IP**: `18.185.139.191`
- **Instance Type**: `t3.micro` (Ubuntu 24.04 LTS)
- **User**: `ubuntu`
- **Project Directory**: `/home/ubuntu/TRMNL-ZH`
- **TRMNL Endpoint**: `http://18.185.139.191/api/display`
- **Static Image**: `http://18.185.139.191/generated/screen.png`

---

## 2. Accessing the Server (SSH)

From your local terminal, navigate to the folder containing your `.pem` key:

```bash
ssh -i "trmnl-key.pem" ubuntu@18.185.139.191
or
ssh -i "trmnl-key.pem" ubuntu@ec2-18-185-139-191.eu-central-1.compute.amazonaws.com
```

---

## 3. Managing the Application (systemd)

The app runs as a background service called `trmnl.service`.

- **Check status**: `sudo systemctl status trmnl.service`
- **Restart (after code/env changes)**: `sudo systemctl restart trmnl.service`
- **Stop**: `sudo systemctl stop trmnl.service`
- **Start**: `sudo systemctl start trmnl.service`
- **View Live Logs**: `sudo journalctl -u trmnl.service -f`

---

## 4. Web Server Management (Nginx)

Nginx acts as the "bridge" (Reverse Proxy) between the web and your app.

- **Check status**: `sudo systemctl status nginx`
- **Restart**: `sudo systemctl restart nginx`
- **Check configuration for errors**: `sudo nginx -t`
- **Nginx Error Logs**: `sudo tail -f /var/log/nginx/error.log`
- **Nginx Access Logs**: `sudo tail -f /var/log/nginx/access.log`

---

## 5. Updating the Code

Since you are using Git, the easiest way to update is:

1. **On the server**:

   ```bash
   cd /home/ubuntu/TRMNL-ZH
   git pull origin main
   sudo systemctl restart trmnl.service
   ```

2. **Uploading single files (SCP)**:
   ```bash
   scp -i "your-key.pem" filename.py ubuntu@18.185.139.191:/home/ubuntu/TRMNL-ZH/
   ```

---

## 6. Troubleshooting & Common Fixes

### "403 Forbidden" or "Permission Denied"

If the TRMNL device (or your browser) cannot see the image at `/generated/screen.png`, Nginx likely lacks permission to read your folder.
**The Fix**:

```bash
sudo usermod -aG ubuntu www-data
chmod g+x /home/ubuntu
chmod g+x /home/ubuntu/TRMNL-ZH
chmod -R g+rx /home/ubuntu/TRMNL-ZH/generated
sudo systemctl restart nginx
```

### "401 Unauthorized"

This is **NORMAL** when visiting via a browser. The server requires an `ID` header. To test it manually, use `curl`:

```bash
curl -H "ID: A0:85:E3:6B:CB:80" http://18.185.139.191/api/display
```

### "Connection Refused" or "Timeout"

1. Check if the app is running: `sudo systemctl status trmnl.service`.
2. Check the **AWS Security Group**: Ensure **Inbound Rules** allow **HTTP (Port 80)** from `0.0.0.0/0`.
3. Check the internal firewall: `sudo ufw status`. If active, run `sudo ufw allow 80/tcp`.

---

## 7. Key Configuration (.env)

Always ensure your `.env` on the server has the correct **Public IP**:

```env
BASE_URL="http://18.185.139.191"  # No 's' and no ':8000'
TRMNL_DEVICE_ID="A0:85:E3:6B:CB:80" # Must match device
```

Location: `/home/ubuntu/TRMNL-ZH/.env`

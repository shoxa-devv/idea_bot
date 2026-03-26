#!/bin/bash

# Start Cloudflare Tunnel in the background
echo "🌐 Starting Cloudflare Tunnel..."
cloudflared tunnel --url http://localhost:8080 > ./tunnel.log 2>&1 &

# Wait for the tunnel to be established and get the URL
echo "⏳ Waiting for Cloudflare Tunnel URL..."
max_attempts=45
attempt=0
while [ $attempt -lt $max_attempts ]; do
    # Try to extract from tunnel.log
    TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' ./tunnel.log | head -n 1)
    
    if [ ! -z "$TUNNEL_URL" ]; then
        echo "✅ Tunnel established at: $TUNNEL_URL"
        
        # Update WEB_BASE_URL in .env
        sed -i "s|WEB_BASE_URL=.*|WEB_BASE_URL=$TUNNEL_URL|" .env 2>/dev/null || echo "WEB_BASE_URL=$TUNNEL_URL" >> .env
        
        export WEB_BASE_URL=$TUNNEL_URL
        break
    fi
    sleep 2
    attempt=$((attempt+1))
done

if [ -z "$WEB_BASE_URL" ]; then
    echo "⚠️  Failed to extract Cloudflare Tunnel URL. Check tunnel.log content below:"
    cat ./tunnel.log
fi

# Show the tunnel output for debugging
tail -n 20 ./tunnel.log

# Start the bot via run.sh
echo "🚀 Starting Prank Bot via run.sh..."
exec ./run.sh

"""
WebSocket client for Feedback Bot.
Connects to Django site and receives feedback submissions via WebSocket.
"""

import asyncio
import websockets
import json
import logging
import os
from datetime import datetime
from typing import Optional
from hmac_utils import verify_hmac, create_signed_message

logger = logging.getLogger(__name__)


class FeedbackBotWSClient:
    """
    WebSocket client that connects to Django site.
    Receives feedback submissions and sends results back.
    """
    
    def __init__(self, telegram_bot):
        """
        Initialize WebSocket client.
        
        Args:
            telegram_bot: Instance of Telegram bot for sending messages
        """
        self.ws_url = os.getenv('SITE_WS_URL')
        self.ping_interval = int(os.getenv('WS_PING_INTERVAL', '20'))
        self.reconnect_backoff = int(os.getenv('RECONNECT_BACKOFF', '5'))
        self.telegram_bot = telegram_bot
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        
        if not self.ws_url:
            raise ValueError("SITE_WS_URL not set in environment")
        
        logger.info(f"WebSocket client initialized: {self.ws_url}")
    
    async def start(self):
        """
        Start WebSocket client with auto-reconnect.
        Runs indefinitely, reconnecting on connection loss.
        """
        self.running = True
        logger.info("🚀 Starting WebSocket client...")
        
        while self.running:
            try:
                await self._connect_and_run()
            except websockets.exceptions.WebSocketException as e:
                logger.error(f"❌ WebSocket error: {e}")
                await asyncio.sleep(self.reconnect_backoff)
            except Exception as e:
                logger.exception(f"❌ Unexpected error: {e}")
                await asyncio.sleep(self.reconnect_backoff * 2)
    
    async def stop(self):
        """Stop WebSocket client gracefully."""
        logger.info("🛑 Stopping WebSocket client...")
        self.running = False
        if self.ws:
            await self.ws.close()
    
    async def _connect_and_run(self):
        """Connect to WebSocket and run main loop."""
        logger.info(f"🔌 Connecting to {self.ws_url}...")
        
        async with websockets.connect(
            self.ws_url,
            ping_interval=None,  # We handle ping ourselves
            close_timeout=10
        ) as ws:
            self.ws = ws
            logger.info("✅ WebSocket connected to site!")
            
            # Start ping task
            ping_task = asyncio.create_task(self._ping_loop())
            
            try:
                # Main message loop
                async for message in ws:
                    try:
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Error handling message: {e}", exc_info=True)
            
            except websockets.exceptions.ConnectionClosedOK:
                logger.info("✅ WebSocket connection closed normally")
            
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ WebSocket connection closed: {e}")
            
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
    
    async def _handle_message(self, raw_message: str):
        """
        Handle incoming message from site.
        
        Args:
            raw_message: JSON string from WebSocket
        """
        try:
            message = json.loads(raw_message)
            msg_type = message.get('type')
            
            logger.debug(f"📥 Received message type: {msg_type}")
            
            if msg_type == 'new_feedback':
                await self._process_feedback(message)
            
            elif msg_type == 'ping':
                await self._send_pong()
            
            else:
                logger.warning(f"Unknown message type: {msg_type}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
        
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    async def _process_feedback(self, message: dict):
        """
        Process new feedback submission from site.
        
        Args:
            message: Feedback message with data, ts, nonce, sig
        """
        msg_id = message.get('id')
        data = message.get('data')
        ts = message.get('ts')
        nonce = message.get('nonce')
        sig = message.get('sig')
        
        logger.info(f"📝 Processing feedback: id={msg_id}, feedback_id={data.get('feedback_id')}")
        
        # Verify HMAC signature
        if not verify_hmac(ts, nonce, data, sig):
            logger.error(f"❌ Invalid HMAC signature for message {msg_id}")
            await self._send_result(
                msg_id,
                ok=False,
                error="Invalid HMAC signature"
            )
            return
        
        logger.debug(f"✅ HMAC verified for message {msg_id}")
        
        # Send to Telegram
        try:
            result = await self.telegram_bot.send_feedback_to_telegram(
                feedback_id=data.get('feedback_id'),
                telegram_id=data.get('telegram_id'),
                telegram_username=data.get('telegram_username', ''),
                telegram_first_name=data.get('telegram_first_name', ''),
                nickname=data.get('nickname', ''),
                category=data.get('category'),
                message=data.get('message'),
                created_at=data.get('created_at'),
                source=data.get('source', 'website')
            )
            
            # Send success result back to site
            await self._send_result(
                msg_id,
                ok=True,
                result={
                    'ticket_id': result['ticket_id'],
                    'message_id': result['message_id'],
                    'sent_at': result['sent_at']
                }
            )
            
            logger.info(f"✅ Feedback {result['ticket_id']} sent to Telegram successfully")
        
        except Exception as e:
            logger.error(f"❌ Failed to send to Telegram: {e}", exc_info=True)
            await self._send_result(
                msg_id,
                ok=False,
                error=str(e)
            )
    
    async def _send_result(self, msg_id: str, ok: bool, result: dict = None, error: str = None):
        """
        Send feedback processing result back to site.
        
        Args:
            msg_id: Original message ID
            ok: Success status
            result: Result data (if successful)
            error: Error message (if failed)
        """
        if not self.ws:
            logger.error("Cannot send result: WebSocket not connected")
            return
        
        payload = {
            'id': msg_id,
            'ok': ok,
            'result': result,
            'error': error
        }
        
        # Create signed message
        signed_message = create_signed_message('feedback_result', payload)
        
        # Send to site
        try:
            await self.ws.send(json.dumps(signed_message))
            logger.debug(f"📤 Result sent for message {msg_id}: ok={ok}")
        
        except Exception as e:
            logger.error(f"Failed to send result: {e}")
    
    async def _send_pong(self):
        """Send pong response to site."""
        if not self.ws:
            return
        
        try:
            await self.ws.send(json.dumps({'type': 'pong'}))
            logger.debug("🏓 Pong sent")
        except Exception as e:
            logger.error(f"Failed to send pong: {e}")
    
    async def _ping_loop(self):
        """
        Send periodic ping to keep connection alive.
        Runs every WS_PING_INTERVAL seconds.
        """
        while True:
            await asyncio.sleep(self.ping_interval)
            
            if not self.ws:
                break
            
            try:
                await self.ws.send(json.dumps({'type': 'ping'}))
                logger.debug("🏓 Ping sent")
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                break


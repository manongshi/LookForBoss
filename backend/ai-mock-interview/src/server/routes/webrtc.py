# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

"""WebRTC 相关路由。

Modified for FindBoss: local ICE, failed-offer cleanup and abandoned-session expiry.
"""
import json
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration
from aiortc.rtcrtpsender import RTCRtpSender
import asyncio

from src.utils.webrtc import HumanPlayer
from src.avatars.factory import create_avatar
from src.utils.logging import logger
from src.server.state import state
from src.server.utils import randN


async def offer(request):
    """处理 WebRTC offer 请求"""
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    sessionid = randN(6)
    state.add_session(sessionid, None)
    logger.info('sessionid=%d, session num=%d', sessionid, len(state.avatar_streams))
    pc = None
    try:
        avatar_stream = await asyncio.get_running_loop().run_in_executor(
            None, create_avatar, request.get('avatar_config', state.config), state.model,
            request.get('avatar_data', state.avatar), sessionid
        )
        state.add_session(sessionid, avatar_stream)
        # FindBoss only exposes this runtime on loopback; no public STUN is needed.
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
        state.add_peer_connection(pc)
        state.session_pcs[sessionid] = pc

        async def release():
            if pc.connectionState != "closed":
                await pc.close()
            state.remove_peer_connection(pc)
            state.remove_session(sessionid)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("Connection state is %s", pc.connectionState)
            if pc.connectionState == "failed":
                await release()
            elif pc.connectionState == "closed":
                state.remove_peer_connection(pc)
                state.remove_session(sessionid)
            elif pc.connectionState == "disconnected":
                async def expire_disconnected():
                    await asyncio.sleep(15)
                    if pc.connectionState == "disconnected":
                        await release()
                asyncio.create_task(expire_disconnected())

        player = HumanPlayer(avatar_stream)
        pc.addTrack(player.audio)
        pc.addTrack(player.video)
        capabilities = RTCRtpSender.getCapabilities("video")
        preferences = [codec for name in ("H264", "VP8", "rtx") for codec in capabilities.codecs if codec.name == name]
        pc.getTransceivers()[1].setCodecPreferences(preferences)
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        async def expire_unclaimed():
            await asyncio.sleep(35)
            if pc.connectionState not in ("connected", "closed"):
                await release()
        asyncio.create_task(expire_unclaimed())
        return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "sessionid": sessionid})
    except BaseException:
        if pc is not None:
            await pc.close()
            state.remove_peer_connection(pc)
        state.remove_session(sessionid)
        raise


async def disconnect(request):
    params = await request.json()
    sessionid = params.get('sessionid')
    pc = state.session_pcs.get(sessionid)
    if pc:
        await pc.close()
        state.remove_peer_connection(pc)
    state.remove_session(sessionid)
    return web.json_response({'ok': True})

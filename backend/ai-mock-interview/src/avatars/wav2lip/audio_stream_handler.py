# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

"""Wav2Lip 音频流处理器 - 提取 Mel 频谱特征"""
import time
import torch
import numpy as np

import queue
from queue import Queue

from src.avatars.audio_stream_handler import BaseAudioStreamHandler
from src.avatars.wav2lip import audio


class LipAudioStreamHandler(BaseAudioStreamHandler):
    """Mel 频谱特征提取器
    
    用于 Wav2Lip Avatar 模型，提取 Mel 频谱特征用于唇形同步。
    """

    def run_step(self):
        """执行一步音频特征提取"""
        ############################################## extract audio feature ##############################################
        # get a frame of audio
        for _ in range(self.batch_size * 2):
            frame, type, eventpoint = self.get_audio_frame()
            self.frames.append(frame)
            self.frame_types.append(type)
            # put to output
            self.output_queue.put((frame, type, eventpoint))
        # context not enough, do not run network.
        if len(self.frames) <= self.stride_left_size + self.stride_right_size:
            return
        
        # Synthetic silence needs no STFT/Mel work. Keep one feature marker per
        # batch so the inference worker still consumes the matching audio frames.
        # Include both context strides: speech near a batch boundary must retain
        # its real features until it leaves the entire analysis window.
        if all(frame_type == 1 for frame_type in self.frame_types):
            self.feat_queue.put(None)
        else:
            inputs = np.concatenate(self.frames)  # [N * chunk]
            mel = audio.melspectrogram(inputs)
            left = max(0, self.stride_left_size * 80 / 50)
            mel_idx_multiplier = 80. * 2 / self.fps
            mel_step_size = 16
            i = 0
            mel_chunks = []
            while i < (len(self.frames) - self.stride_left_size - self.stride_right_size) / 2:
                start_idx = int(left + i * mel_idx_multiplier)
                if start_idx + mel_step_size > len(mel[0]):
                    mel_chunks.append(mel[:, len(mel[0]) - mel_step_size:])
                else:
                    mel_chunks.append(mel[:, start_idx : start_idx + mel_step_size])
                i += 1
            self.feat_queue.put(mel_chunks)
        
        # discard the old part to save memory
        context_size = self.stride_left_size + self.stride_right_size
        self.frames = self.frames[-context_size:] if context_size else []
        self.frame_types = self.frame_types[-context_size:] if context_size else []

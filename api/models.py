"""Shared Pydantic models used by both the REST routes and the MCP handlers."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from common.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to convert to speech")
    voice: str = Field(default=DEFAULT_VOICE, description="Voice identifier")
    rate: str = Field(default=DEFAULT_RATE, description="Speaking rate, e.g. +10%, -20%")
    pitch: str = Field(default=DEFAULT_PITCH, description="Voice pitch, e.g. +10Hz, -5Hz")
    volume: str = Field(default=DEFAULT_VOLUME, description="Volume, e.g. +10%, -20%")
    output_filename: Optional[str] = Field(default=None, description="Custom output filename")


class AudioInfo(BaseModel):
    filename: str
    file_size_bytes: int
    file_size_human: str
    url: str


class TTSResponse(BaseModel):
    success: bool
    content: str
    audio: AudioInfo
    voice: dict
    timestamp: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str

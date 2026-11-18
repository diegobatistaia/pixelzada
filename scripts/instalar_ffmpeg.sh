#!/usr/bin/env bash
# Instala o ffmpeg rápido: binário estático (BtbN, ~1 min) e só cai no apt se o download falhar.
# O apt chegou a levar mais de 10 min em 18/11 e atrasou os clipes das lives (Diego aprovou a troca).
set -u
command -v ffmpeg > /dev/null && exit 0
URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz
if timeout 120 curl -fsSL "$URL" -o /tmp/ffmpeg.tar.xz && tar -xJf /tmp/ffmpeg.tar.xz -C /tmp; then
  sudo install -m 755 /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffprobe /usr/local/bin/
  ffmpeg -version | head -1 && exit 0
fi
echo "binário estático falhou; usando apt"
sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg > /dev/null

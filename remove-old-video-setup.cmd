@echo off
title 3zT Agent - remove old video/image generation setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\remove_old_generation.ps1"

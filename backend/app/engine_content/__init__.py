"""ComfyUI content management - Phase A (read-only).

The GUI is a studio on top of ComfyUI, not a bundle of it: the user points the app
at their own install (`comfyuiFolder`) and the app reports which module content
(custom nodes, model files) is present. See docs/COMFYUI_CONTENT.md.

Nothing in this package writes, downloads or executes anything - later phases add
explicit, user-triggered installs/downloads on top of these audits.
"""

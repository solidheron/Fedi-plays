# Fediverse Plays GameBoy on PeerTube

This project enables a **Twitch Plays-style** system for controlling a **GameBoy emulator (PyBoy)** through **chat messages** in a **PeerTube livestream**. Viewers can send commands in the chat, which are interpreted and executed in the emulator.

## Features
- 🕹️ **Control GameBoy games via chat commands**
- 🎥 **Reads chat messages from a PeerTube stream** using Playwright
- 📜 **Supports command repetition (e.g., `left*3`, `a*2`)**
- 💾 **Automatic state saving/loading every 30 minutes**
- ⚡ **Efficient game execution with PyBoy**

---

## Installation

### 1️⃣ Prerequisites
Ensure you have the following installed:
- **Python 3.9+**
- **pip** (Python package manager)

### 2️⃣ Install Dependencies
Run the following command to install required Python packages:
```bash
pip install pyboy playwright
```
After installing Playwright, run:
```bash
playwright install
```

### 3️⃣ Download a GameBoy ROM
Place your `.gb` or `.gbc` ROM file in the project directory and update the script with its path.

### 4️⃣ Configure the Chat URL
Update the following line in `main()` with your PeerTube chat URL:
```python
await page.goto("https://your-peertube-instance/chat-url", timeout=60000)
```

---

## Usage

Run the script with:
```bash
python main.py
```
The script will:
1. Start the **GameBoy emulator** (PyBoy)
2. Load the **last saved game state** (if available)
3. Connect to the **PeerTube chat** using Playwright
4. Listen for **chat commands** and control the game accordingly

---

## Supported Commands
Users can send **single or repeated commands** in chat. The recognized commands are:

| Command  | Action  |
|----------|--------|
| `up`    | Move up |
| `down`  | Move down |
| `left`  | Move left |
| `right` | Move right |
| `a`     | Press A button |
| `b`     | Press B button |
| `start` | Press Start button |
| `select`| Press Select button |

### Repeated Commands
Users can **repeat** a command by adding `*N`, where `N` is the number of times:
```text
left*3   # Moves left 3 times
b*2      # Presses 'B' twice
```
(Maximum repetition: 10)

---

## Troubleshooting

### Playwright Fails to Load Page
If the script times out while loading the chat, check your PeerTube instance URL and ensure it's accessible.

### Commands Aren't Being Processed
1. Ensure **messages are in the correct format**.
2. Check that the **emulator is running properly**.

---

## Contributing
Feel free to submit **issues** or **pull requests** to improve the script!

---

## License
This project is licensed under the **MIT License**. See `LICENSE` for details.


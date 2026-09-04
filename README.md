# ✨ Yuki - Advanced Discord Bot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python)
![Discord.py](https://img.shields.io/badge/discord.py-2.0+-5865F2?style=for-the-badge&logo=discord)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

A powerful, feature-rich Discord bot designed for server management, protection, and customization.

[Features](#features) • [Commands](#commands) • [Installation](#installation) • [Support](#support)

</div>

---

## 🎯 Features

### 🛡️ **Server Protection**
- **Anti-Nuke System** - Comprehensive protection against raids and unauthorized actions
- **Automatic threat detection** with real-time response
- **Whitelist management** for trusted users and roles
- **Audit log monitoring** for suspicious activities

### 🎨 **Customization**
- **Reskin functionality** - Customize bot appearance per server (name & avatar)
- **Webhook-based message delivery** for seamless integration
- **Vanity system** - Set phrases and reward roles based on user status

### 👮 **Moderation Tools**
- **Role restoration** - Auto-restore user roles on rejoin
- **UWU-lock** - Text transformation features
- **Jail system** - Isolated moderation channels
- **Permission management** - Granular control over server access

### 🔐 **Premium Features**
- **Authorization system** - Manage premium server subscriptions
- **Transfer management** - Move premium access between servers
- **Dual-mode billing** - Monthly and one-time purchase options

### ℹ️ **Utilities**
- **Uptime tracking** - Real-time bot status monitoring
- **Invite management** - Easy bot deployment
- **Bot statistics** - Comprehensive usage metrics
- **Multi-command support** - Hybrid command system

---

## 🚀 Commands

### Moderation
```
setmod          - Enable moderation features
unsetmod        - Disable moderation features
jail            - Isolate problematic members
```

### Customization
```
reskin set      - Set custom bot name
reskin avatar   - Set custom bot avatar
reskin delete   - Remove reskin settings
vanity set      - Set vanity phrase
vanity role     - Assign role based on vanity phrase
```

### Server Protection
```
antinuke        - Configure anti-nuke settings
whitelist       - Manage whitelist for trusted users
```

### Information
```
botinfo         - Display bot statistics
uptime          - Check bot uptime
ping            - Check bot latency
invite          - Get bot invite link
```

---

## 💾 Database Integration

Yuki uses **PostgreSQL** for persistent data storage:
- Authorization tracking
- Server settings & preferences
- User reskins & customizations
- Anti-nuke configurations
- Moderation logs

---

## 🔧 Technology Stack

- **Python 3.8+** - Core language
- **discord.py 2.0+** - Discord API wrapper
- **PostgreSQL** - Database backend
- **Async/Await** - Non-blocking operations

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/0xkrul/Yuki-AI.git
cd Yuki-AI

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
# Create .env file with:
# DISCORD_TOKEN=your_token_here
# DATABASE_URL=postgresql://user:password@localhost/yuki

# Run the bot
python main.py
```

---

## 🔗 Links

- **[Invite Yuki](https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot%20applications.commands)**
- **[Support Server](https://discord.gg/ZTTXMkk8ua)**

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

<div align="center">

**Made with ❤️ by 0xkrul**

*Efficient. Reliable. Powerful.*

</div>
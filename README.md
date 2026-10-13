<p align="center"><img src="docs/icon.png" width="160" alt="Kataware icon"></p>

# Kataware（かたわれ）

[日本語](#日本語) | [English](#english)

Windows / Mac 対応の Bluetooth 機器バッテリー残量表示アプリ。分割キーボードは左右それぞれの残量を同時に表示します。

Battery level monitor for Bluetooth devices on Windows and Mac. Shows both halves of split keyboards at once.

<sub>Claude Code で作成 / Built with [Claude Code](https://claude.com/claude-code) — [制作について / About](#制作について--about)</sub>

> アイコンは、一対の「片割れ」を表す家紋「二つ巴」に、七宝文様を織り込み、あえて途切れさせた金の輪（破れ）を重ねたものです。
>
> The icon is a *futatsu-domoe* — two interlocking commas, a pair of "kataware" (halves) — woven with the *shippo* pattern and framed by a deliberately broken gold ring.

---

## 日本語

### できること

- 接続中の Bluetooth 機器（キーボード・マウス・ゲームパッドなど）のバッテリー残量を表示
- **分割キーボード（ZMK など）は左右両方の残量を同時に表示**
  — OS の設定画面では片側しか見えない残量も確認できます
- Windows はタスクトレイ（通知領域）、Mac はメニューバーに常駐（ウィンドウは開きません）
- アイコンに残量を数字またはバーで表示、クリックで機器ごとの詳細
- 残量が少なくなったら通知（10% / 20% / 30% / オフ）
- 設定・ログはこの PC の中だけに保存し、外部への通信は一切しません

### 対応機器

Bluetooth LE の標準「Battery Service」で残量を公開している機器に対応しています。
多くの Bluetooth キーボード・マウス・ゲームパッドが該当します。

- バッテリー情報が 2 つ以上ある機器（分割キーボードなど）は「左 / 右」に分けて表示
- 1 つの機器は「本体」として表示
- 次の機器は表示できません
  - 旧来の Bluetooth（Classic）方式だけで残量を送る機器（一部のイヤホン・ヘッドホンなど）
  - PC とペアリング・接続されていない機器

### ダウンロード

[Releases ページ](https://github.com/kyonccc/Kataware/releases/latest) の「Assets」から OS に合ったファイルをダウンロードしてください。インストールは不要です。

| OS | ファイル |
| --- | --- |
| Windows 10 / 11 (64bit) | `Kataware-Windows-x64.exe` |
| Mac (Apple シリコン M1〜) | `Kataware-macOS-AppleSilicon.zip` |
| Mac (Intel) | `Kataware-macOS-Intel.zip` |

#### Windows の初回起動

1. `Kataware-Windows-x64.exe` を置き場所を決めて（おすすめ: `%LOCALAPPDATA%\Programs\Kataware`。OneDrive で同期されるデスクトップやダウンロードフォルダーは避ける）ダブルクリック
   — 後から移動しても、移動先で一度起動すれば「ログイン時に起動」の登録先も自動で更新されます
2. 「Windows によって PC が保護されました」と出たら **詳細情報 → 実行**（署名なしアプリのため）
3. **ウィンドウは開きません。** 通知領域（右下の `^` の中）にアイコンが出ます（初回は「起動しました」の通知が出ます）。
   常に見えるようにするには、アイコンをタスクバーへドラッグしてください

#### 目立たない場所に置いて自動起動する（おすすめ・Windows）

デスクトップなどに .exe を置きたくない場合は、次の場所にしまっておけます。
OneDrive の同期対象にならず、普通のアプリもよく入っている場所です。

```
%LOCALAPPDATA%\Programs\Kataware\Kataware-Windows-x64.exe
```

1. 起動中なら、通知領域のアイコンのメニューから **終了**
2. エクスプローラーのアドレス欄に `%LOCALAPPDATA%\Programs` と入力して Enter
3. **新規作成 → フォルダー** で `Kataware` フォルダーを作り、その中に `Kataware-Windows-x64.exe` を移動
4. .exe を右クリック → プロパティ → 「全般」タブ下部の **許可する** にチェック → OK
5. .exe をダブルクリックして起動し、メニューの **ログイン時に起動** にチェック
   （すでにチェック済みなら、この場所で一度起動するだけで登録先が自動で切り替わります）

これで次回からは PC の起動時に自動で常駐します。.exe を開く必要はありません。

#### 通知領域のアイコンも隠したいとき（Windows）

設定 → 個人用設定 → タスクバー → **その他のシステム トレイ アイコン** で Kataware をオフにすると、アイコンは「^」の中にしまわれます。
残量は「^」を開けばいつでも確認でき、残量低下の通知も届きます。
（逆にオンにすると、タスクバーに常に表示されます）

#### タスクバーにピン留めして起動したい場合（Windows）

ダウンロードした .exe をそのままピン留めすると、「アプリケーション制御ポリシーによってこのファイルがブロックされました」と出て起動できないことがあります。
Windows がインターネットから来たファイルに付ける印（Mark of the Web）が原因です。

1. ピン留めを外す
2. `Kataware-Windows-x64.exe` を右クリック → プロパティ → 「全般」タブ下部の **許可する** にチェック → OK
   （PowerShell なら `Unblock-File .\Kataware-Windows-x64.exe`）
3. もう一度タスクバーにピン留め

ピン留めしなくても、メニューの **ログイン時に起動** を有効にすれば PC 起動時に自動で常駐します。

#### Mac の初回起動

1. zip を展開して `Kataware.app` を「アプリケーション」フォルダへ移動
2. **右クリック → 開く → 開く** で起動（署名なしアプリのため）
   - macOS 15 以降でブロックされた場合: システム設定 → プライバシーとセキュリティ → 下部の「このまま開く」
   - 「壊れているため開けません」と出た場合: ターミナルで `xattr -dr com.apple.quarantine /Applications/Kataware.app`
3. 「Bluetooth の使用を求めています」と出たら **許可**
4. メニューバーにアイコンが出ます

### 使い方

アイコンをクリック（Windows は右クリックでも可）するとメニューが開きます。

```
moNa2
    左: 85%
    右: 72%
最終更新 12:34
─────────
今すぐ更新
左右の設定（メイン側）  ▶  メイン(セントラル)は左側 / 右側
アイコンに表示する機器  ▶
アイコンの表示形式      ▶  数字 / バー
更新間隔                ▶  1 / 5 / 15 / 30 分
残量低下の通知          ▶
ログイン時に起動
ログを開く
終了
```

#### 左右が逆に表示されるとき

分割キーボードには、PC と直接つながる「セントラル（メイン）」側と、セントラル経由でつながる「ペリフェラル」側があります。
どちらが左か右かはファームウェアによって違うため、**左右の設定（メイン側）** で切り替えてください（機器ごとに保存されます）。

#### ペリフェラル側（片側）の残量が表示されないとき（ZMK）

zmk-config の `.conf` に以下を追加してファームウェアを書き直してください。

```
CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y
CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY=y
```

書き込み後は、PC / Mac の Bluetooth 設定でキーボードを一度削除してから再ペアリングしてください（機器情報が PC 側にキャッシュされているため）。

### しくみ

- 機器の Battery Service (0x180F) にある **Battery Level 特性 (0x2A19) をすべて** 読み取ります。
  ZMK はセントラル側の残量と、ペリフェラル側の残量（説明 "Peripheral 0"）を別々の特性で公開しているため、両方を表示できます。
- **Windows**: WinRT の Bluetooth LE API を使用。接続中の機器だけに短い読み取りを行い、読み取り後は毎回接続オブジェクトを破棄します（常時接続や通知購読をしないため、スリープ復帰や再接続でエラーが溜まりません）。
- **Mac**: CoreBluetooth で「すでに Mac に接続されている機器」を取得して読み取ります（再ペアリング不要）。
- すべての処理にタイムアウトがあり、1 台でエラーが起きてもアプリは落ちず、最後に読めた値を表示し続けます。

### 設定・ログの保存場所

| OS | 場所 |
| --- | --- |
| Windows | `%APPDATA%\Kataware\` |
| Mac | `~/Library/Application Support/Kataware/` |

不具合があったときは、メニューの **ログを開く** で表示される `kataware.log` を添えて Issue を作成してください。

---

## English

### Features

- Shows the battery level of connected Bluetooth devices (keyboards, mice, gamepads, …)
- **Shows both halves of split keyboards (ZMK etc.) at the same time**
  — the OS settings only ever show one of them
- Lives in the Windows system tray / macOS menu bar (no window)
- Tray icon shows the levels as numbers or bars; click for per-device details
- Low battery notifications (10% / 20% / 30% / off)
- Settings and logs stay on your computer; the app never talks to the internet

### Supported devices

Any device that exposes its battery through the standard Bluetooth LE **Battery Service** — most Bluetooth keyboards, mice and gamepads.

- Devices with two or more battery values (split keyboards) are shown as "Left / Right"
- Devices with one battery value are shown as a single level
- Not supported:
  - Devices that report battery only over Bluetooth Classic (some earbuds / headphones)
  - Devices that are not paired and connected to this computer

### Download

Get the file for your OS from the **Assets** of the [latest release](https://github.com/kyonccc/Kataware/releases/latest). No installation required.

| OS | File |
| --- | --- |
| Windows 10 / 11 (64-bit) | `Kataware-Windows-x64.exe` |
| Mac (Apple silicon) | `Kataware-macOS-AppleSilicon.zip` |
| Mac (Intel) | `Kataware-macOS-Intel.zip` |

#### First launch on Windows

1. Put `Kataware-Windows-x64.exe` somewhere permanent (recommended: `%LOCALAPPDATA%\Programs\Kataware`) and double-click it — if you move it later, launch it once from the new place and the login item follows
2. If "Windows protected your PC" appears, click **More info → Run anyway** (the app is not code-signed)
3. **No window opens.** The icon appears in the notification area (inside `^` at the bottom right). Drag it onto the taskbar to keep it visible

#### Keeping it out of sight (recommended, Windows)

Store the app in `%LOCALAPPDATA%\Programs\Kataware\Kataware-Windows-x64.exe` (not synced by OneDrive):
quit the app, type `%LOCALAPPDATA%\Programs` in the Explorer address bar, create a `Kataware` folder, move the .exe there,
right-click it → Properties → **Unblock**, launch it once and enable **launch at login** (ログイン時に起動) in the menu.
To hide the tray icon as well: Settings → Personalization → Taskbar → **Other system tray icons** → turn Kataware off (it stays available under `^`).

#### Pinning to the taskbar (Windows)

If a pinned shortcut fails with "This file was blocked by your organization's application control policy", Windows is blocking the downloaded file (Mark of the Web).
Unpin it, right-click `Kataware-Windows-x64.exe` → Properties → check **Unblock** → OK (or run `Unblock-File .\Kataware-Windows-x64.exe` in PowerShell), then pin it again.
You can also just enable **launch at login** (ログイン時に起動) in the menu instead of pinning.

#### First launch on Mac

1. Unzip and move `Kataware.app` to Applications
2. **Right-click → Open → Open** (the app is not notarized)
   - On macOS 15+: System Settings → Privacy & Security → "Open Anyway"
   - If macOS says the app "is damaged": run `xattr -dr com.apple.quarantine /Applications/Kataware.app`
3. Allow Bluetooth access when asked
4. The icon appears in the menu bar

### Usage

Click the icon to open the menu: battery levels, refresh, left/right setting, icon device, icon style (numbers / bars), poll interval, low battery notification, launch at login, open log, quit. (The menu is in Japanese.)

#### Left and right are swapped

A split keyboard has a "central" half (connected to the computer) and a "peripheral" half. Which one is left depends on the firmware — pick the central side in **左右の設定（メイン側）** in the menu. The choice is saved per device.

#### The peripheral half does not show up (ZMK)

Add the following to your zmk-config `.conf`, reflash, then remove and re-pair the keyboard on your computer:

```
CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y
CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY=y
```

### How it works

- Reads **every** Battery Level characteristic (0x2A19) in the device's Battery Service (0x180F). ZMK publishes the central's level and each peripheral's level (described as "Peripheral N") as separate characteristics.
- **Windows**: WinRT Bluetooth LE APIs; only connected devices are queried with short reads, and every WinRT object is disposed after each poll.
- **Mac**: CoreBluetooth `retrieveConnectedPeripherals` — reads keyboards already connected to macOS without re-pairing.
- Every operation has a timeout; one misbehaving device never crashes the app, and the last good values stay visible.

Settings and logs: `%APPDATA%\Kataware\` (Windows), `~/Library/Application Support/Kataware/` (Mac). Please attach `kataware.log` (menu → ログを開く) when reporting an issue.

---

## 開発者向け / Development

```bash
python -m pip install ".[dev]"
python -m pytest                # unit tests
python -m kataware --demo       # run with fake devices (no Bluetooth needed)
python -m kataware --once       # read once and print raw characteristics
python packaging/make_icons.py && pyinstaller --noconfirm packaging/kataware.spec   # build
```

GitHub Actions builds the app on Windows and macOS (Apple silicon / Intel) virtual machines, then runs the unit tests and a self-test of the packaged app (`--self-test`). A release `v<version>` is published only when every platform passes — triggered by a `v*` tag or a push whose commit message contains `[release]`.

## 制作について / About

Kataware は、[Claude Code](https://claude.com/claude-code)（Anthropic の AI コーディングツール）を使って作成しました。
kyonccc が「分割キーボードの左右両方の残量を、Windows でも Mac でもエラーなく確認したい」という思想・要件と、名前やアイコンの方向性を示し、
設計・実装・テスト・リリース作業は Claude Code が行っています。

Kataware was built with [Claude Code](https://claude.com/claude-code), Anthropic's AI coding tool.
kyonccc provided the idea, the requirements and the direction for the name and icon; the design, code, tests and releases were produced by Claude Code.

## ライセンス / License

[MIT](LICENSE) © 2026 kyonccc

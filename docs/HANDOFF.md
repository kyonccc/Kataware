# 引き継ぎメモ（Kataware）

最終更新: 2026-11-07（v1.5.0 時点）

## 目的と現状

- **目的:** Windows / Mac で、分割キーボード（オーナーは ZMK の moNa2 を使用）の左右両方の電池残量と、
  他の Bluetooth 機器の残量を表示する常駐アプリ。OS の設定画面では片側しか見えない問題を解決する。
- **リポジトリ:** 本体は **kyonccc/Kataware**（main ブランチ）。kyonccc/zmk-split-battery は最初に見本として
  使ったフォーク（元製作者あり）で、現在は使っていない（`claude/zen-wright-w25m3q` に旧名 SplitBattery 版が残るだけ）。
- **公開済み:** GitHub Releases は v1.3.1 が最新（Windows .exe / macOS zip ×2、SHA256SUMS.txt、ビルド証明付き）。
- **未公開:** v1.4.0（Store 対応・安定性改善）と v1.5.0（銀ベゼルのリング表示・充電中表示）は main に入っているが、
  GitHub Release も Store 提出もまだ。CI の成果物（Actions の Artifacts）にはある。
- **Microsoft Store:** 提出用 MSIX を CI で自動作成済み（識別名は仮）。**オーナー本人の作業待ち**:
  1. https://storedeveloper.microsoft.com で個人開発者として無料登録
  2. Partner Center でアプリ名「Kataware」を予約
  3. 「製品 ID」ページの Package/Identity/Name・Package/Identity/Publisher・Package/Properties/PublisherDisplayName を共有
     → リポジトリ変数 `MSIX_IDENTITY_NAME` / `MSIX_PUBLISHER` / `MSIX_PUBLISHER_DISPLAY_NAME` に設定して作り直す
- **実機確認:** Windows 11 のオーナー PC で、moNa2 左右・ERGO M575SP・Keychron K2 Max・Keychron Nape Pro・Nothing Ear の
  表示を確認済み（〜v1.3.x）。v1.4.0 以降（Store 版・リング・充電表示）は実機未確認。Mac は実機未確認。

## 決まったこと（理由）

- **名前は Kataware（片割れ）:** 分割キーボードの「対の片方」。誤って Katawari と書いた経緯あり（正しくは kataware）。
- **アプリアイコン:** 二つ巴＋巴の中に七宝文様＋2 か所途切れた金の輪（破れ）。藍色の背景。「シンプルだけど奥ゆかしい」
  （`packaging/make_icons.py` がコードで生成）。
- **通知領域アイコンの初期設定は「リング」:** 銀ベゼルの時計風。左半分＝左手、右半分＝右手（下から上へ伸びる）、
  中央に数字（同梱フォント Inter Display Bold、OFL）。他に「数字」「バー」も選べる。
  経緯: 数字表示が面白味がない → 案 C（半月リング）を採用 → 立体化して銀ベゼルを選択。
- **残量の色:** 51% 以上 緑 / 21〜50% オレンジ / 低下通知のしきい値（初期 20%）以下 赤 / 未接続 グレー。
- **充電中表示:** 機器は残量しか送らないため推定。直近の最低値から +2 以上で「充電中」（⚡）、
  ピークから 2 以上下がるか、100% 未満で 30 分上昇なしで解除。充電中は低下通知を出さない。数分遅れることは README に明記。
- **残量の読み方:** Battery Service の Battery Level 特性を全部読む（ZMK は "Peripheral N" の説明付きで片側を追加公開）。
  読めない機器は Windows の DEVPKEY_Bluetooth_Battery（設定画面と同じ値）で補完（Windows のみ）。
- **更新:** 5 分ごと（1/5/15/30 分）＋ Windows は接続・切断イベントで 3 秒後に再読込。未接続の機器は最後の値をグレーで保持
  （再起動後も devices.json で保持、メニューから消せる）。
- **配布方針:** Windows は **Microsoft Store を本命**（スマート アプリ コントロールに止められないため）。GitHub の .exe も継続。
  新しい .exe を公開すると SAC の評判がリセットされるので、v1.4/1.5 の GitHub 公開は Store 提出と同時にする予定。
- **セキュリティ:** 通信なし・読み取りのみ。Actions はコミット SHA で固定、Dependabot 有効、リリースに SHA256 とビルド証明。
- **クレジット:** README に「Claude Code で作成、kyonccc は思想・要件・方向性を提示」と明記（オーナーの希望）。
  ライセンスは MIT © 2026 kyonccc。

## 未決のこと

- アプリアイコン（二つ巴）を立体化するか（試作は見せたが未回答）。
- Store の説明文・スクリーンショット・年齢区分の準備（Partner Center 登録後）。
- Dependabot の更新 PR 5 件（checkout 7 / setup-python 7 / upload-artifact 7 / download-artifact 8 / attest-build-provenance 4）。
  メジャー更新なので CI を通してから取り込む。
- メニューの英語対応（世界向けには最優先と提案済み、未着手）。Android 版は検討のみ。

## 次にやること（優先順）

1. オーナーの Partner Center 値を受け取り、リポジトリ変数に設定 → 正式な MSIX を作成 → 説明文・スクリーンショット・
   プライバシーポリシー URL（`PRIVACY.md`）を用意して提出を手伝う。
2. 提出と同時に GitHub Release v1.5.0 を公開（コミットメッセージに `[release]`）。
3. 実機確認の依頼: リングの見え方、充電中 ⚡ の表示、Store 版の「ログイン時に起動」（StartupTask）。
4. Dependabot PR の確認・取り込み。
5. アイコン立体化の判断、英語対応。

## 注意点・ハマりどころ

- **ビルドとテストは GitHub Actions の仮想環境で行う**（`.github/workflows/build.yml`）。windows-latest / macos-15 /
  macos-15-intel。各 OS でユニットテスト → PyInstaller ビルド → ビルドしたアプリで `--self-test`。
  Windows ではさらに onedir ビルド → MSIX 作成（`packaging/build_msix.ps1`）→ 自己署名のテスト MSIX を実際にインストールし、
  実行エイリアス `kataware.exe --self-test` でパッケージ内の動作を確認する。
- 仮想環境には Bluetooth が無い。自己テストは「アダプターなし」を正常系として扱い、WinRT / CoreBluetooth の API 存在確認と
  デバイス列挙（probe）で代わりに検証する。実機の読み取りはオーナーに確認してもらう。
- **リリース:** タグの push はこの環境から拒否される。コミットメッセージに `[release]` を含めて main に push すると、
  全 OS 合格時のみ `v<__version__>` のリリースが作られる。バージョンは `src/kataware/__init__.py` と `pyproject.toml` の 2 か所。
- **pywinrt は 3.x に固定**（4.x は API 非互換）。`pyproject.toml` で `>=3.2,<4`。
- MSIX はレジストリと %APPDATA% が仮想化される。Store 版は LocalState に保存し、自動起動は StartupTask（`src/kataware/winpkg.py`）。
  Store 版から GitHub 版の Run キーは消せない（README で事前にオフにするよう案内）。
- macos-14 ランナーは起動しなくなった（macos-15 に変更済み）。
- ローカル確認: `python -m pytest -q`、`xvfb-run -a python -m kataware --self-test report.json`、`python -m kataware --demo`。
- CI の状況確認は公開 API（`curl https://api.github.com/repos/kyonccc/Kataware/actions/...`）と GitHub MCP のジョブログ取得で行った。
- PyInstaller の 1 ファイル .exe は会社 PC の EDR（WithSecure）や SAC に止められやすい。会社 PC では無理に回避しない方針。
- オーナーが GitHub 上で README を直接編集することがある。push 前に `git pull --rebase`。

## 主なファイルの場所・作業ブランチ

- 作業ブランチ: **kyonccc/Kataware の main**（直接 push してきた）
- `src/kataware/` — `app.py`（トレイ UI・メニュー）、`monitor.py`（ポーリング・状態・充電推定）、`icon.py`（アイコン描画、リング）、
  `models.py`（左右判定）、`config.py`（設定・保存先）、`platform_utils.py`（通知・自動起動・移行）、`winpkg.py`（MSIX 判定・StartupTask）、
  `cli.py`（起動・`--self-test`）、`backends/windows.py`・`backends/macos.py`・`backends/demo.py`、`assets/`（Inter フォント＋OFL）
- `packaging/` — `kataware.spec`（PyInstaller、`KATAWARE_ONEDIR=1` で onedir）、`make_icons.py`、`build_msix.ps1`、
  `msix/AppxManifest.xml.in`
- `tests/test_core.py`、`README.md`（日英）、`PRIVACY.md`、`LICENSE`

## オーナーの好み

- 日本語でやり取り。専門用語は短く補足してほしい。結論→理由→手順の順で、表でまとめると喜ぶ。
- 和のモチーフ（二つ巴・七宝・金継ぎ・破れ）が好き。「シンプルだけど奥ゆかしい」もの。数字表示には遊び心がほしい。
- 試作画像を複数見て選ぶ進め方を好む。小さいサイズ（16〜24px）での見え方も一緒に示す。
- 無料で多くの人に使ってもらえたら楽しい、という動機。費用のかかる手段は慎重。
- 「自分が作ったものとして出したい」が、実際の作成は Claude Code であることを明記したい。
- セキュリティ・法律面（家紋の利用など）を気にする。会社 PC のセキュリティは回避しない。

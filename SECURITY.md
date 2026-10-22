# Security Policy

English | [日本語](#セキュリティポリシー)

## Supported versions

Security fixes are made for the latest release only.

## Reporting a vulnerability

Please do not report security vulnerabilities in public issues, discussions or pull requests.

Report them privately through GitHub instead: open the repository's **Security** tab and choose **Report a vulnerability** ([direct link](https://github.com/gyuro-dev/pytest-casebook/security/advisories/new)). Include the version, the steps to reproduce, and the impact you expect.

This is a personal project maintained on a best-effort basis. We will acknowledge your report as soon as we can, keep you updated on the fix, and credit you in the advisory if you wish.

## What to keep in mind when using pytest-casebook

Case files are code. A case file can run commands (`command:`), import and call Python functions (`call:`) and send HTTP requests (`request:`), and conftest.py hooks run with your permissions. Run only case files and conftest.py files that you trust, as you would any other test code.

---

## セキュリティポリシー

[English](#security-policy) | 日本語

### 対象の版

セキュリティの修正は、最新の版にだけ行います。

### 脆弱性の報告

脆弱性は、公開の issue・discussion・pull request には書かないでください。

GitHub の非公開の報告を使ってください。リポジトリの **Security** タブから **Report a vulnerability** を選びます（[直接のリンク](https://github.com/gyuro-dev/pytest-casebook/security/advisories/new)）。\
版、再現の手順、想定される影響を書いてください。

個人のプロジェクトのため、できる範囲で対応します。\
報告を受け取ったらできるだけ早く返事をし、修正の状況をお知らせします。\
希望があれば、公開する advisory に報告者としてお名前を載せます。

### 使うときに気をつけること

ケースファイルはコードです。\
ケースファイルはコマンドを実行し（`command:`）、Python の関数を import して呼び（`call:`）、HTTP のリクエストを送れます（`request:`）。\
conftest.py の hook も、実行した人の権限で動きます。\
ほかのテストのコードと同じく、信頼できるケースファイルと conftest.py だけを実行してください。

# Temiz kaynak RAR paketi

RAR, doğrulanmış bir commit'in tracked kaynaklarını taşır. Python ortamı, Git veritabanı/oturum durumu, host MCP ayarı, özel makine/vendor dosyaları veya kaynak calibration varlıkları içermez. Arşiv uzantısı değiştirilmiş ZIP değildir; gerçek RAR olarak bütünlük ve extraction denetlenir. Bu bir geliştirme snapshot'ıdır; destek sınırları [güncel rapordadır](../reports/VERIFICATION.md).

## Başka bilgisayarda başlatma

Arşivi aç ve içindeki universal-hmi-agents klasöründe Git ve Python 3.14+ ile çalış. RAR Git geçmişi taşımadığı için yeni ajan baseline'ını yerel olarak oluştur:

```text
git init
git add .
git commit -m "Initialize imported Universal HMI Agents source snapshot"
```

Bu commit için kullanıcının o bilgisayardaki Git kimliği gerekir. Mevcut bir repo içinde init yapma; paketi ayrı klasörde başlat. Paket yanında verilen source commit ve SHA manifesti provenance kanıtıdır; yeni repo'nun HEAD'i eski commit SHA'sına eşit olmak zorunda değildir. Önceki checkpoint devralınmaz.

Windows kurulumu:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m universal_hmi.cli doctor
.venv/Scripts/python.exe scripts/verify.py
.venv/Scripts/python.exe scripts/configure_mcp.py --format codex
```

Son komut yeni bilgisayarın interpreter ve checkout yolundan MCP TOML ayarını üretir; eski bilgisayarın ayar dosyası kopyalanmaz. İstemciye bağlantı kaydını kullanıcı veya yetkili ajan ekler. [MCP örneği](../scripts/codex_config.toml.example), [taşıma rehberi](PORTABILITY.md).

POSIX sunucuda sh scripts/setup.sh ve .venv/bin/python kullanılır. Linux/macOS runtime kabulü ayrıca gerekir; Windows extraction/kurulum testi başka OS'yi kabul etmez. İlk kurulum pinned bağımlılıkları indirmek için internet ister.

## Yeni makine işi

Ajan [AGENTS.md](../AGENTS.md), [SYSTEM_PROMPT.md](../SYSTEM_PROMPT.md), [INDEX.md](../INDEX.md) ve [başlangıç talimatını](../prompts/START_NEW_PROJECT.md) okur; yeni görev zarfı/checkpoint kurar. Makine workspace'i projects altında ayrılır. Gerçek native hedef, donor/property kanıtları, tag kaynağı ve onaylar ilgili makine projesinin girdileridir; temiz genel pakete eklenmez.

Driver namespace'inde generic repo yalnız tarafsız registered sözleşmeyi taşır. Vendor DLL veya eski kurulum path'i runtime girdisi değildir. Source/model/serialized-version/driver/storage eşleşmesi yeniden doğrulanır; paket aktarmak UNVERIFIED bir profile'ı qualified yapmaz.

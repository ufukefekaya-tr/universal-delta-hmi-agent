# Başka bilgisayara ve sunucuya taşıma

Çekirdek ve stdio MCP bağımsız Git repo'sudur. Runtime yazarın kullanıcı adı, disk yolu, vendor kurulumu veya başka makine projesine bağlı değildir. Yeni host'ta **Git ve Python 3.14+** gerekir. Native kapsam taşımayla genişlemez: özgün SYNTHETIC/0.0 transaction'ı yanında, exact source/schema/calibration witness'i ve gerçek insan onayıyla mevcut literal text/geometriye bağlı `.dps/.dpa` offline aday kaydedilebilir. Diğer source içeriği full raw/final-byte karşılaştırmasıyla korunur. Full HMI program writer tamamlanmamıştır; default gerçek profiller UNVERIFIED'dır. Source-local deney veya unknown owner retention vendor/Alarm davranış kabulü değildir.

## Repo ve yerel ortam

Temiz RAR aktarımı için [paket başlangıcı](CLEAN_PACKAGE.md) uygulanır. Arşiv yalnız committed tracked kaynak snapshot'ıdır; .git, eski .venv, host config, checkpoint ve makine girdileri taşınmaz. Yeni agent baseline'ı ayrı klasörde yeni Git başlangıcıyla kurulur. Optional [adres sözleşmesi](DRIVER_ADDRESSES.md) repo içindeki tarafsız factual registry'yi kullanır; vendor DLL veya kurulum path'i runtime gereksinimi değildir.

Source-local kontrol üretimi yeni host'ta [CONTROL_GENERATION.md](CONTROL_GENERATION.md) ile kullanılır. `calibrate_controls.py` workspace-relative kaynak ve property kanıtlarını okur; yazar bilgisayarının vendor yolu runtime gereksinimi değildir. Genel repo taşınır, özel source/calibration/witness dosyaları ilgili projenin yetkili girdileri olarak ayrıca taşınır. Bu girdiler aktarılmadığında eski profil kimliği tek başına üretim yetkisi vermez.

Tercih edilen yol repo'yu clone etmektir. URL veya kaynak repo yolu yeni host'un erişebildiği konum olmalıdır:

```text
git clone --no-local "<repository-url-or-full-repo-path>" universal-hmi-agents
```

Dosya kopyasıyla taşıyorsan tracked dosyaları ve gerçek `.git` dizinini birlikte koru. Worktree'nin başka checkout'a işaret eden `.git` pointer dosyasını bağımsız repo sanma; bağımsız clone kullan. `.venv`, `.local` ve eski host'un üretilmiş MCP/client ayarını kopyalama. Editable install yeni checkout'un konumuna bağlanır; checkout sonradan başka konuma taşınırsa o konumda ortamı yeniden oluştur.

`git archive` veya ham source ZIP normalde `.git` içermez. Bu ZIP yalnız kaynak aktarımıdır: committed HEAD/control-plane ve session guard önkoşulunu karşılamaz. ZIP ile yeni repo gerekiyorsa kanonik yeni-repo bootstrap kuralına göre yerel Git başlatılır ve ilk control-plane commit'i yapılır; ardından yeni baseline/epoch/envelope/checkpoint üretilir. Eski çalışma checkpoint'i yeni yetki olarak kabul edilmez. Bu ek adımı önlemek için clone veya tam bağımsız Git repo kopyası önerilir.

## Yeni host'ta kurulum

Repo klasöründe Windows:

```powershell
python --version
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m universal_hmi.cli doctor
.venv/Scripts/python.exe scripts/verify.py
```

Repo klasöründe POSIX sunucu:

```sh
python3 --version
sh scripts/setup.sh
.venv/bin/python -m universal_hmi.cli doctor
.venv/bin/python scripts/verify.py
```

Seçilen Python interpreter 3.14+ olmalıdır. POSIX script gerekirse `PYTHON` ortam değişkenindeki interpreter'ı kullanır. Script'ler repo kökünü kendi konumlarından çözer, yeni `.venv` oluşturur; `requirements.lock` yükler ve paketi `--no-deps --no-build-isolation -e` ile editable kurar. Build backend setuptools 84.0.0 da sabittir. `pywin32` platform marker'ı yalnız Windows'ta kurulur; POSIX runtime Windows paketi gerektirmez.

Kurulum vendor GUI veya PLC aracını kurmaz, istemci global ayarını değiştirmez. Opsiyonel başsız görsel smoke Python runtime kabulünden ayrıdır; ek Node/Playwright/Chromium bağımlılıkları ayrıca doğrulanır. Docker veya görünür GUI başlatmak temel runtime önkoşulu değildir.

scripts/build_profiles.py tarihsel fixture utility'sidir; setup tarafından çağrılmaz ve mevcut profile registry'sini yeniden üretme adımı değildir.

## MCP istemcisi ve çalışma dizini

Boş-hedef yazıcısının commit5d7afae / revision4174a715 kaynağı yeni, bağımsız Windows checkout ve sıfırdan kurulan venv'de507/507 testi aynı47 source hash'iyle geçti.30 lock pin'i,691 ayrı Git object, no origin/alternates, unrelated caller ve editable import gerçek ortamda salt-okunur denetlendi. [Kayıt](../reports/relocation_verification.json), [ortam incelemesi](../reports/RELOCATION_507_REVIEW.md). Bu aynı fiziksel Windows host'unda taşımadır; Linux/macOS/ikinci PC/vendor/panel kanıtı değildir.

[Boş hedef üretimi](BLANK_PROGRAM.md) de proje-local kaynak/calibration/property dosyalarına bağlıdır. Genel çekirdekte sabit donor yolu yoktur. Başka host'ta yeni ortam/MCP ayarı oluşturulur; yetkili özel workspace girdileri ayrı taşınır ve bütün SHA'lar yeniden doğrulanır. Core repo'nun kopyası tek başına özel kaynakları içermez.

Genel client örneğinin başlatma sözleşmesi:

```text
command: python
args: ["-m", "universal_hmi.cli", "serve"]
```

Bu `python` paketin yeni host'ta kurulu olduğu interpreter olmalıdır. Client başka bir cwd'den çalışabilir: varsayılan registry `profiles/`, çalışma alanı `projects/`, editable checkout'un kendi konumundan çözülür. Client cwd'sine veya eski bilgisayarın yollarına dayanılmaz.

Yeni venv interpreter'ını kesin seçmek için **yeni host'ta**, repo klasöründe:

```powershell
.venv/Scripts/python.exe scripts/configure_mcp.py --format codex
.venv/Scripts/python.exe scripts/configure_mcp.py --format json
```

POSIX'te aynı komutların interpreter'ı `.venv/bin/python` olur. İstenirse `--workspace` yeni host'taki ayrı proje kökünü seçer. Üretici yalnız stdout'a yeni host'un interpreter/profile/workspace yollarını içeren JSON veya TOML basar; client dosyasına yazmaz. Üretilen mutlak yollar taşınabilir core'a gömülmez. Eski host'un çıktısını taşımak yerine her yeni host'ta yeniden üret; client'a uygun tabloyu o host'ta uygula. Repo örnekleri otomatik global kayıt değildir.

Kaynağa bağlı existing-owner aday için varsayılan registry yerine **bu proje/source revision'ında üretilmiş profile folder** seçilir. Repo kökünden, yeni ortamın interpreter'ıyla örnek:

```text
python -m universal_hmi.cli --profiles "projects/<project-id>/contracts/v001/profiles" serve --workspace "projects/<project-id>"
```

Global `--profiles`, `serve` öncesindedir. Relative workspace/profile argümanları bu örnekte repo kökünden çözülür; farklı client cwd'sinde yeni host'un çözülmüş konumları seçilir. Core'a yazar PC yolu gömülmez. `scripts/calibrate_source.py` yalnız yeni üç JSON sözleşmesi üretir; existing source'un SHA'sı, raw model/serialized Version/çözünürlük, owner/prefix hashes ve workspace-relative calibration yolu birbirine bağlıdır. Serialized Version executable editor build değildir. Her projenin ayrı registry/workspace'i kullanılır. [Aday adımları](NATIVE_CANDIDATES.md) ve [DOP-B ajan başlangıcı](../prompts/DOP_B_PROGRAMMER.md) gerçek komut ve approval kapsamını açıklar.

## Proje girdileri ve insan kabulü

Özel native kaynaklar, tags/adresler, onaylar ve insan kanıtları ignored proje-local alandır. Clone bunları otomatik taşımaz. Kendi girdilerini ayrıca, yetki/provenance/lisans sınırıyla aktar; core'a müşteri dosyası veya lisansı belirsiz vendor fixture ekleme. Yeni host'ta input SHA, proje workspace, profile ve task baseline/scope yeniden doğrulanır.

Kaynağa bağlı sözleşmelerin relative yolları aynı proje yapısında korunabilir; yeni host'ta hash/freshness ve görev yetkisi yeniden doğrulanır. Başka kaynağa witness/profile taşımak, `qualified` yazmak veya provenance etiketini değiştirmek yetki vermez. Exact insan onayı source/profile/design/bindings/operations/calibration SHA'larına bağlıdır. Neutral onay istisnası actual SYNTHETIC/0.0 kaynağa özgüdür; gerçek vendor dosyası etiketiyle aşılmaz. Native-preserved nesne/hash/geometri ve retained raw Order yalnız preservation kanıtıdır; vendor layer/alarm semantiği veya yeni OS kabulü değildir.

V1 test modelleri zaten root tarafından seçildi: DOP-B07S411 (`dop_b07s411_dopsoft2`) ve DOP-110IS (`dop_110is_diascreen`). Taşıma için test modeli tekrar seçtirilmez. Yeni müşteri projesinin exact profile/driver contract'i proje-local kalır.

Runtime için vendor IDE gerekmez. İnsan vendor open/compile/simulate kabulü, vendor yazılımının desteklediği OS/bilgisayarda yapılır; Linux runtime testi vendor IDE desteği veya panel kabulü değildir. Existing-owner preview yalnız text/coordinate intent'idir; retained native appearance render edilmez. Tam emitter geliştirmesi, gerçek iki-native pilot, vendor ve fiziksel kabul açık kalır.

## Doğrulama durumu

| Katman | Durum / kanıt sınırı |
|---|---|
| Windows mevcut host | Güncel Python/framework/stdio run/revision root [test raporunda](../reports/python_tests.json) kaydedilir; local suite native/vendor/panel veya fresh-host kabulü değildir. [Unit milestone](../reports/NATIVE_UNIT_MILESTONE.json) kendi tarihsel unit revision'ını kanıtlar, güncel candidate kaynağını değil. |
| Windows başka konuma taşınmış repo + yeni venv | 225-test tarihsel taşıma (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/225/relocation_verification.json`)/test (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/225/relocation_tests.json`), 263-test tarihsel taşıma (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/263/relocation_verification.json`)/test (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/263/relocation_tests.json`) ve 297-test tarihsel unit taşıma (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/297/relocation_verification.json`)/test (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/297/relocation_tests.json`) yalnız kendi revision'larında OFFLINE_PASS'tır. Güncel source-pinned candidate kaynağının fresh-clone/actual-environment kabulü PENDING'dir; önceki proof bu kaynağa aktarılmaz. |
| Linux runtime | NOT_RUN. Önceki oturumda Docker daemon kullanılamadı; GUI başlatılmadı. POSIX script ve platform marker mevcut olsa da Linux'ta tam çalıştı denmez. |
| macOS runtime | NOT_RUN; POSIX kurulum yolu verilmesi OS test kabulü değildir. |
| Native/vendor/physical | Ayrı tam feature geliştirmesi ve insan kabulü gerekir; host taşıma bunları kapatmaz. |

Tarihsel Windows kanıtları `cee48fc3ea2176a1926d7a5d1c29bb3c4a765951`/`6b4d74e10126d334547baa831d1b44e391cf003c3c691f0f81446a4f057ed9b3` ve `e60fdf6bf6829d52866769889da9e5982c161b45`/`8d8b416bea7055a4f51afb3f854fbbe922f61f4e483179b8e243e158c9c46e8c` kaynak/test revision'larına aittir. Tarihsel 225-test fresh clone `55ef69390bb51fabfba5f1603e9b8477488a47b1` source commit'i ve `c25e69fe9a6401e4d24a0b036345b5978d7478eb90581320f1b3652689d41931` test revision'ıyla OFFLINE_PASS'tır; proof commit'i `771001c9796f9d9ec9128ef195e37745c919481f`'tir.

Tarihsel 263-test Windows relocation `215e4267a7f3694e7a71822e005ca4e20f3e9125` source commit'i ve `0b2eeee4f6ee03fab00b287c5cf17dc0e291555b1b61a5bb8e696fab43c95b8d` revision'ında OFFLINE_PASS (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/263/relocation_verification.json`)/test raporu (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/263/relocation_tests.json`) kaydeder: aynı 40 kaynak hash'i, sıfır failure/error/skip, process exit 0 ve pip check 0. Bağımsız checkout/new venv, eski ortamın PATH/PYTHONPATH'ten çıkarılması, yeni source'a çözülen import ve unrelated caller cwd raporlanmıştır. Aynı fiziksel Windows host'taki ayrı checkout/yeni ortamın bağımsız actual-environment denetimi kendi revision'ında PASS'tır: gerçek .git, origin/alternates yokluğu, 40 hash/revision, aynı sıra ve kimliklerle 263 test, 30 pin, editable direct_url/import ve eski checkout'un PATH/sys.path'te bulunmaması doğrulanmıştır. Proof kapanışı `7cfe5fb40d150c54f40eff236722f09df5d69595` commit'i/checkpoint'te kayıtlıdır; tarihsel 263 raporları (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/263/README.md`) yeni unit kaynağının kabulü değildir.

Tarihsel unit fazı source ve conceptual renderer'ı değiştirmiştir. Linked unit text owner, inactive identity-conversion baseline, stable index overflow checks ve raw embedded-caption helper'ın sınırları [ARCHITECTURE](ARCHITECTURE.md#numeric-unit-compiler-subset) içindedir. Tarihsel unit proof [unit milestone](../reports/NATIVE_UNIT_MILESTONE.json)/[review](../reports/NATIVE_UNIT_REVIEW.md) ve exact 297 taşıma raporu (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/297/relocation_verification.json`)/test raporu (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/297/relocation_tests.json`) ile okunur. Güncel candidate kaynağı için root suite ve bağımsız reviewer aynı exact revision/hash/test listesine bağlanmalı; yeni Windows fresh clone ve actual-environment denetimi local suite'den ayrıca yapılmalıdır. Eski checkout/venv/client config yokluğu, pins/pip check/import ve unrelated cwd yeniden doğrulanır. Yeni proof kendi [manifest](../reports/manifest.json) hash eşitliğine, Git parent/exact paths ve tek yazarlı checkpoint ile scoped commit'e bağlanır; 401-test eski kaynak kabulü kendi exact proof’unda korunur; yeni436 kaynak ayrıca sınanır.

Önceki FrameworkReady, macro/Alarm ve layout milestone'ları kendi kaynaklarında korunur. Page baseline/Order/appearance guard veya unit subset'inin varlığı OS qualification ya da vendor flat-style/native UnitDirection/font/enum/pixel kabulü sağlamaz. Local suite PASS yeni host kabulü değildir. Linux/macOS NOT_RUN, tam G2/G3 compiler/qualification, G4 iki gerçek native pilot ve G5/G7 insan kabulü açık kalır. Private input/30 gerçek read-only unit-owner holdout kaynakları/assets genel repo'ya aktarılmaz; holdout korunumu production/selected-model/vendor/pixel veya public Alarm IR/view/history desteği açmaz.

## Tarihsel 297-test birim kaynağı — temiz Windows ortamı

Tarihsel source commit `12a655975cec085d19f741ab96e61196b41cb5c8`, bağımsız clone/yeni venv'de **297/297** benzersiz testi 43.695 saniyede, 0 failure/error/skip ve aynı40 kaynak hash'i / revision `765c6460d932d0ba66ab4e7ade29f10350b5c8c95546c2ef4c19c63af328ed1d` ile geçti. Tarihsel 297 taşıma raporu (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/297/relocation_verification.json`), tarihsel test raporu (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/297/relocation_tests.json`). Eski venv kopyalanmadı; yeni module import'u ve pip check0 doğrulandı. Bağımsız actual-environment denetimi bu tarihsel source'ta PASS: gerçek ayrı .git/origin/alternates, yeni isolated venv/editable direct_url/import, unrelated caller, eski PATH/sys.path/PYTHONPATH/PYTHONHOME yokluğu, 30 pin, pip check0, aynı40 hash/297 ID sırası ve host-neutral loglar doğrulandı. Aynı fiziksel Windows host'unda ayrı konum/ortam testidir; güncel candidate kaynağına, Linux/macOS'a, ikinci fiziksel PC'ye, native/vendor/panel veya tam V1 kabulüne aktarılmaz.

## Yeni literal sayfa kaynağı — temiz Windows ortamı

Source `23ffbc8c4854827e9f563c75fcc30de19ab31a99`,41 hash ve revision `4ecbb67a8057c97a46132eacfa9c5a18fd360b9eb2c48a552bf0c1dc29815e79`: ayrı checkout/yeni venv, unrelated caller ile436/436 benzersiz test,0failure/error/skip. Yeni import/pip check0 ve actual Git/origin/alternates/new venv/editable direct_url/unrelated caller/old PATH/sys.path/PYTHONPATH/PYTHONHOME yokluğu,30 pin ve41hash bağımsız actual-environment audit ile doğrulandı. [Güncel taşıma raporu](../reports/relocation_verification.json), [test](../reports/relocation_tests.json). Eski401 proof history/401 (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/401/README.md`) içinde byte eşit tarihsel korunur. Bu aynı fiziksel Windows host’unda farklı konum/ortam testidir; ikinci PC/Linux/macOS/vendor/panel kabulü değildir.

`literal_page_generation` helper/registry/workspace sözleşmeleri host path’i içermez. Yeni source/donor/profile ve onay bağları yeniden doğrulanır. [Giriş rehberi](LITERAL_PAGE_GENERATION.md). Literal graph dependency UNKNOWN ve tam program writer açık kalır; ortam kurulması native yürütme kanıtı değildir.

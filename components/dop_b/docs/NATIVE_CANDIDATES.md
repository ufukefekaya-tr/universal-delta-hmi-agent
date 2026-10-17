# Kaynağa bağlı native aday düzenleme

DIAScreen için ayrı [kaynak-kontrol klonlama yolu](DIASCREEN_CONTROL_APPEND.md) da vardır. `calibrate_diascreen_controls.py` ve `diascreen_control_append` modu dört immutable donörü yeni ID/geometri/primary buton yazılarıyla kopyalar; kaynak adres ve makroları ortak tutar. Bu kılavuzun aşağıdaki mevcut inert text/geometri yolu değişmemiştir. Kontrol kopyası yeni adres, blank program, runtime veya native görünüm kabulü değildir.

DIAScreen'in opak global prefix'i için ayrı [V2 kaynak politikası](DIASCREEN_EXISTING_CANDIDATE.md) vardır. Yalnız exact DOP-107WV gözlem kimliği/source hash ve inert same-extent caption/geometri kapsamındadır; default V1 veya DOP-B yetkisi genişlemez. Vendor/program-writer kabulü değildir.

Mevcut kod, gerçek bir DOP-B `.dps` veya DOP-100 `.dpa` kaynağındaki **önceden var olan, açıkça seçilmiş sabit metinlerin başlığını ve geometrisini** ayrı bir native adaya yazabilir. Bu dar yol tam HMI program yazarı değildir: `program_writer_complete=false`. Yeni sayfa, yeni kumanda nesnesi veya çalışan PLC bağlantısı üretmez. Kullanıcının kaynağı değiştirilmez.

Bu kılavuz `scripts/calibrate_source.py` ve dokuz dosya odaklı MCP aracının mevcut sözleşmesini anlatır. Kodun varlığı vendor kabulü değildir; exact revision/test/bağımsız inceleme sonuçları [güncel doğrulama raporundan](../reports/VERIFICATION.md) okunur. Önceki sürümün PASS sonucu bu koda otomatik taşınmaz.

## İzin verilen değişiklik

| Alan | Aday yolundaki sınır |
|---|---|
| Kaynak ve hedef | Kaynağın gerçek family marker'ı, model kimliği, raw sürümü, çözünürlüğü ve SHA'sı birlikte bağlanır. `.dps`/`.dpa` uzantısı tek başına hedef kanıtı değildir. |
| Düzenlenebilir nesne | Kaynaktaki `Type=10 / SubType=6`; tek `State`, açık `Value=0`, `ReadVar=None`, `WriteVar=None`. Mevcut offset/visibility operandları da `None` olmalıdır. Element veya State içinde dolu çalıştırılabilir macro bulunamaz. |
| Metin | Yalnız mevcut primary `wTextLen0` UTF-16LE başlığı; durum/language seçimi `0`. Yeni başlık terminal NUL dahil **aynı byte uzunluğunda** olmalıdır. |
| Geometri | Aynı nesnenin `X`, `Y`, `Width`, `Height` tamsayıları. Her native scalar'ın ASCII byte uzunluğu korunur; ortak geometri kontrolleri de geçmelidir. |
| Diğer nesneler | `native_preserved`: bütün Element ve bağlı State extent'inin SHA'sı ile mevcut geometrisi aynen korunur. Düzenlenmez, kopyalanmaz veya silinmez. |
| Sayfalar | Bütün kaynak sayfaları, isimleri, çözünürlükleri ve nesne sırası aynen korunur. Yeni sayfa, yeniden sıralama veya yeniden adlandırma yoktur. |
| Görünüm ve davranış | Native font, renk, resim, layer, şeffaflık, State ve davranış kaynaktan korunur. Bunların doğruluğu ya da anlamı bu yolda yeniden kurulmaz. |
| Kaynak kaynakları | Driver, adres, tag, macro, alarm, global prefix, Order, opak tail ve temsil edilmeyen içerik korunur. Bunlar için yeni IR eklenmez. |

Aynı caption/geometri byte extent'ini korumak kayıt sınırlarını sabit tutar; opak offsetlerin veya retained metadata'nın vendor semantiği `UNVERIFIED` kalır. Örneğin kaynak `X=120` ise `121` aynı scalar extent'indedir; `99` aynı extent'te değildir. Metnin karakter sayısı tek başına yeterli değildir: `len(text.encode('utf-16-le')) + 2` mevcut caption blob uzunluğuna eşit olmalıdır. Ek Unicode düzlemindeki karakterler iki UTF-16 code unit kaplar. Sığdırmak için metni sessiz kesme, boşlukla doldurma veya native veri tipini değiştirme.

Değişmemiş aday bütün kaynak dosya byte'larını korur. Değişmiş adayda karşılaştırılan sınır, decoded native payload'daki beklenen metin/geometri değişikliği ve diğer içeriğin aynen korunmasıdır. Container sıkıştırması yeniden oluşabilir; sıkıştırılmış dosyanın farklı byte'ları tek başına veri kaybı veya native görünüm doğruluğu kanıtı değildir.

Bu yolun dışında kalan bir isteği doğrudan native patch ile aşma. Adres, buton türü, macro, alarm, font/style veya yeni nesne gerektiğinde geliştirme ve qualification işi açık bırakılır.

## Kaynak kökeni ve sürüm kimliği

Özel native girdiler ve kanıtlar proje-local kalır; genel repo'ya müşteri projesi, görseli veya lisansı belirsiz vendor örneği eklenmez. Kaynağın sahibini, elde edilme yolunu, kullanılabilirlik/yeniden dağıtım sınırını ve SHA'sını bir provenance kaydında belirt. Herkese açık indirme bağlantısı kullanıcının sahipliği veya yeniden dağıtım izni anlamına gelmez. `source_reference` ve `review_reference` açıklayıcı kayıtlara işaret eder; bu iki metin alanının bulunması kullanım hakkını veya inceleme yapıldığını kendiliğinden doğrulamaz.

`--origin user_vendor_project`, gerçek vendor dosyası yolunu ayıran runtime etiketidir; mülkiyet beyanı değildir. `original_neutral_fixture` yalnız özgün tarafsız fixture içindir. Vendor dosyasını bu etiketle yeniden sınıflandırarak approval/production sınırını aşma.

Application içindeki `Version`, **serialized/native format sürümüdür**. Kodun bazı inventory/profile alanlarında bunun adı `editor_version` olsa da bu değer çalıştırılmış DOPSoft veya DIAScreen executable build'ini kanıtlamaz. Kalibrasyon aynı raw değeri `serialized_version` olarak bağlar; `vendor_executable_build=null`, `vendor_acceptance=UNVERIFIED` kalır. Bir `4.x` raw değerinden DOPSoft 4 kullanıldığını çıkarma. Executable adı/build'i insan vendor kanıtında ayrıca kaydedilir.

Kaynak family marker'ı DOPSoft 2 adaptöründe `DOP-B series`, DIAScreen adaptöründe `DOP-100 series` olmalıdır. HMC `.dps` dosyası B kanıtı değildir. Signed raw model kimliği canonical kimliğe çevrilir; bu kimlik tek başına pazarlama model adını veya aile genelindeki uyumluluğu kanıtlamaz. Üretilen profil `SOURCE_PINNED_EXISTING_MODEL` kullanır; seçilmiş V1 modelleri için tamamlanmış profil kabulü değildir.

## Taşınabilir çalışma alanı

[Taşıma kılavuzundaki](PORTABILITY.md) kurulumla yeni host'ta bağımsız checkout ve yeni Python ortamı oluştur. Eski `.venv` veya yazarın MCP/client config'ini taşıma. Aşağıdaki komutlarda `python`, bu checkout'a kurulmuş ortamın interpreter'ıdır; komutlar repo kökünden çalıştırılır. Windows'ta `.venv/Scripts/python.exe`, POSIX'te `.venv/bin/python` açıkça seçilebilir.

Örnek düzen yereldir; `<project-id>` ve kaynak dosya adı bu görev için değiştirilir:

```text
projects/<project-id>/
  inputs/source.dps
  inputs/PROVENANCE.md
  reviews/source-calibration.md
  contracts/v001/
  approvals/
  outputs/v001/
  evidence/
```

Proje workspace'i ve kaynak önceden mevcut olmalıdır. Yerel proje girdileri ignored olduğu için repo clone'u bunları otomatik taşımaz; yetkili girdiler ayrıca aktarılır. Core'a kullanıcı adı, disk harfi, IP veya başka makine projesi yolu gömülmez. İstemcinin görevi için seçtiği workspace/profile konumu yeni host'ta yeniden çözümlenir.

### 1. Kaynağı gerçekten oku

```text
python -m universal_hmi.cli inspect "projects/<project-id>/inputs/source.dps" --family delta_dopsoft2
```

Inventory'den gerçek screen/element kimliklerini, raw native alanları ve başlıkları bul. Sadece ekran görüntüsüne veya sıra numarasına dayanma. Private adres ve müşteri metinlerini genel rapora taşımadan gerekli owner kanıtını proje-local kaydet. Bir parser veya framing hatası varsa sahte kimlik/varsayılan alan ekleyerek aşma.

### 2. Üç kaynağa bağlı JSON sözleşmesi üret

```text
python scripts/calibrate_source.py --workspace "projects/<project-id>" --source "inputs/source.dps" --family delta_dopsoft2 --output "contracts/v001" --edit-text "<screen-id>/<element-id>" --source-reference "inputs/PROVENANCE.md" --review-reference "reviews/source-calibration.md"
```

`--edit-text` gerçek canonical kimliklerle tekrarlanabilir; başında sıfır bulunan veya tekrarlanan kimlikler kabul edilmez. Hiç seçilmezse yalnız korunmuş no-op tasarım oluşur; bu yeni ekran üretimi değildir. Mevcut output sözleşmelerinin üzerine yazılmaz; yeni revision dizini seçilir.

Komut yalnız şunları üretir:

| Dosya | İşlev |
|---|---|
| `contracts/v001/CALIBRATION.json` | Kaynak SHA, family/model/raw sürüm/çözünürlük, schema SHA, köken/review referansları ve seçilmiş owner SHA'ları. |
| `contracts/v001/profiles/existing_owner_v1.json` | Exact kaynağa bağlı profil; bütün prefix section SHA'ları ve kalibrasyon dosyasına workspace-relative yol/raw SHA. |
| `contracts/v001/design.json` | Bütün mevcut sayfa/nesnelerin `native_preserved` temsili. Seçilen metinler de başlangıçta korunmuş nesnedir. |

Çıktı `SOURCE_LOCAL_CONTRACTS_ONLY`, `native_output=NOT_CREATED` olmalıdır. Bu adım `.dps/.dpa` üretmez; driver/editor/pixel/panel qualification yapmaz. Sözleşme veya kaynak sonradan değişirse mevcut session/plan/onay tekrar kullanılamaz.

DIAScreen için aynı akışta family `delta_diascreen`, kaynak `inputs/source.dpa` olur. Uzantı değiştirerek veya B kaynağını DOP-100'e dönüştürerek B desteği kanıtlanmaz.

### 3. MCP'yi bu projenin registry'siyle başlat

```text
python -m universal_hmi.cli --profiles "projects/<project-id>/contracts/v001/profiles" serve --workspace "projects/<project-id>"
```

`--profiles` global argümandır ve `serve` öncesindedir. İstemci aynı interpreter ve argümanlarla stdio sunucusunu başlatır; görevin yollarını yeni host'ta ayarlar. İki kaynak aynı sabit `existing_owner_v1` profil kimliğini üretir; her proje/revision'ın ayrı profile folder ve workspace'i vardır. Bir projenin registry'sini diğer projede kullanma.

### 4. Tasarım niyetini hazırla

Üretilen `design.json` içindeki yalnız seçilmiş uygun owner'ı `kind=text` olarak temsil et; `source_owner_sha256` alanını bu owner'dan kaldır. Bu düzenlenebilir text nesnesinin **yalnız** şu sekiz alanı bulunur:

```text
id, native_id, kind, x, y, width, height, text
```

Kimlikleri kaynaktan koru; `text` alanını actual primary caption'dan başlat. Geometri değişse de caption source text olarak açıkça taşınmalıdır. Font/color/fill, binding, states, behavior, numeric, unit, goto, visibility veya role alanı ekleme. Diğer owner'ların hash, geometri, kimlik ve sırasını değiştirme. `tags`, `macros`, `alarms` boş kalır: bu, kaynakta bunların silindiği anlamına gelmez.

### 5. Dokuz araçla incele, onayla ve yeni aday kaydet

| Araç | Bu görevde kullanım |
|---|---|
| `open_project` | `profile_id=existing_owner_v1`, `source_path=inputs/source.dps`; immutable source ve calibration doğrulanır. Dönen session kimliği kullanılır. |
| `capabilities` | Aynı profile ID'nin dar kapsamını ve kabul sınırlarını oku. `OFFLINE_PASS` capability native/vendor/panel PASS değildir. |
| `inspect` | Session'ın gerçek kaynak inventory'sini incele; owner ve metinleri eşleştir. |
| `plan_changes` | Tam design, sürüme özgü idempotency key; `operations` verilmez veya `null` olur. Exact text/geometri işlemleri tasarımdan derlenir. Aynı key farklı plan için kullanılamaz. |
| `preview` | Plan için `outputs/v001/preview.html`; yeni dosyadır. İnsan niyet incelemesine sunulur. |
| `validate` | Planı kaynak, owner kapsamı, byte extent ve kontrollü fark bakımından doğrula. Findings varsa kapatmadan apply yapma. |
| `apply_plan` | Exact plan için gerçek insan onayını içeren workspace-relative approval dosyası; değişiklik yalnız bellekte uygulanır. |
| `save_as` | Yeni `outputs/v001/candidate.dps`; atomik kayıt, reopen ve bağımsız beklenen byte içeriğiyle karşılaştırma. `.dpa` hedefinde doğru uzantı kullanılır. |
| `diff` | Kaynak/aday SHA, kontrollü işlemler ve yeniden okunmuş inventory. Native görünüm/çalışma kabulü çıkarılmaz. |

Mevcut output kaynağın üstüne yazılmaz. Başarılı bir save'in aynı session'da tekrarı yalnız mevcut dosya SHA'sı receipt ile aynıysa döndürülür; başka çıktıdaki değişiklik üzerine yazılmaz. Stdio stdout'u protokol içindir; günlük ve ek banner basma.

## Önizleme ve gerçek insan onayı

Önizleme `CONCEPTUAL_IR`'dır. Düzenlenebilir literal metin, **metin/koordinat niyetini** gösterir; tarayıcıdaki varsayılan font, renk, dolgu ve fit, korunan native görünümün çizimi değildir. `native_preserved` kutularının `SOURCE OBJECT / NATIVE NOT RENDERED` gösterimi bilinmeyen kaynağı görünür kılar; kaynağın çalışmasını simüle etmez. Placeholder veya üst üste binme incelemesi native glyph/pixel PASS vermez.

Üretim adayı için teknik karşı inceleme, sıralı iki estetik değerlendirme ve insan niyet onayı çalışma kapılarıdır. Native görünüm gerçek vendor ekranında ayrıca insan tarafından kontrol edilir. Eski sentetik tasarım onayı veya başka adayın onayı geçerli değildir.

Approval JSON, `plan_changes` receipt'inden aşağıdaki exact altı değeri taşır:

```text
source_sha256, profile_sha256, design_sha256,
bindings_sha256, operations_sha256, calibration_sha256
```

Bunlara `approved=true`, `authority=direct_human` ve boş olmayan, gerçek insan onayını gösteren `human_reference` eklenir. Ajan yalnız alınmış insan kararını kaydeder; kendisi approval vermez veya referans uydurmaz. Genel approval şablonunun varlığı bu runtime alanlarını doldurmaz. Kaynak/profile/calibration/design/bindings/operations değişince eski receipt stale olur; yeni plan/önizleme/uygun insan onayı gerekir. `neutral_fixture_qualification` istisnası gerçek vendor kaynağına uygulanmaz.

## Teslim ve açık V1 kabulü

Teslim; korunmuş kaynak SHA, calibration/profile/design SHA'ları, plan/onay/diff/save receipt'leri, exact yeni native aday SHA'sı, bağımsız bulgular ve açık işleri içerir. `OFFLINE_NATIVE_CANDIDATE` amacı veya offline integrity PASS yalnız bu metin/geometri adayının kontrollü yazıldığını anlatır. `native_visual`, `vendor`, `physical` bu araçlarca `NOT_RUN` kalır; full production/program writer tamamlanmaz.

İnsan doğru vendor yazılımında ayrı kopyayı açar, kaydeder, derler ve kapsamla ilgili görünümü kontrol eder; panel/PLC kabulü ayrıca yapılır. Vendor yeniden kaydederse yeni SHA alınır, yeniden okunur ve fark tekrar incelenir. Önceki adayın offline/vendor kanıtı yeni SHA'ya otomatik aktarılmaz.

| Açık hedef | Kalan iş |
|---|---|
| G2/G3 | DOP-110IS ve DOP-B07S411 için exact gerçek profil/fixture/driver qualification; tam yeni page/object/tag/numeric/button, font/style/picture/layer/unit/conversion üretimi. Kaynağa bağlı caption adayı bu hedefi kapatmaz. |
| Davranış ve kaynaklar | Gerçek momentary/maintained/set-on/set-off ve comm-loss/restart/feedback; geniş external/alias/REAL/TIME macro/trigger/schedule; yeni alarm entry/trigger/ack/history/storage/retention/lifecycle ve native timestamp/pixel qualification. Bunlar bu aday yolunda değiştirilmez. |
| G4 | Aynı tarafsız ekran sözleşmesinden iki gerçek native pilot. |
| G5 | Exact artifact SHA ve executable build'e bağlı insan open/save/compile/simulation kanıtı. |
| G6 | Bu revision'ın bağımsız teknik incelemesi, gerekli görsel/insan kabulü, temiz ortamda tekrar, manifest ve scoped commit. Eski test sayısı yeni kabul değildir. |
| G7 | İki seçilmiş gerçek panelin okuma/yazma ve davranış kabulü. |
| Taşınabilir runtime | Yeni konum/ortam kabulü exact revision'a bağlanır. Linux/macOS `NOT_RUN`; portable yol tasarımı OS testi değildir. |

[Goals](GOALS.md) ve [destek matrisi](SUPPORT_MATRIX.md) esas kabul kaydıdır. FrameworkReady tam V1 kabulü değildir; `BothFamiliesVendorQualified`, `OperationalBothFamiliesComplete` ve tam V1 tamamlanma hükmü gerekli kanıtlar olmadan verilmez. Yeni ajanın DOP-B görevi için [başlangıç talimatı](../prompts/DOP_B_PROGRAMMER.md) kullanılır.

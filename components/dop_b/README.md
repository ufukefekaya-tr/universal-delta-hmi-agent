# Universal HMI Agents

**0.2.0 DOP-B Headless V1:** mevcut, kaynakla doğrulanmış özelliklerle DPS + kavramsal önizleme + doğrulama paketi. [Kapsam, workflow ve goals](docs/HEADLESS_RELEASE.md) · [Kurulum](docs/HEADLESS_INSTALL.md) · [Güncel kapanış durumu](reports/headless/STATUS.json) · [Bu sürümün kanıtları](reports/headless/VERIFICATION.md). Aşağıdaki eski aşama raporları tarihseldir; güncel kabul STATUS'tadır. Computer Use, vendor IDE ve PLC/panel işlemleri yapılmaz.

Makineden bağımsız, dosya üzerinden çalışan HMI geliştirme ortamı. İlk hedefler **DOP-B / DOPSoft 2** ve **DOP-100 / DIAScreen**. Çekirdek, stdio MCP, tasarım doğrulama, kavramsal önizleme ve ajan çalışma düzeni uygulanmıştır. **FrameworkReady**: ilk framework snapshot'ı Windows'ta bağımsız temiz clone + yeni ortamda 110 testle kabul edildi. Güncel kaynak ve taşıma kanıtının revision'ı [doğrulama raporunda](reports/VERIFICATION.md) ayrılır; eski checkout veya vendor kurulumuna runtime bağımlılığı yok.

**Bu sürüm tam native üretici değildir.** Gerçek `.dps/.dpa` dosyaları okunur ve değişmeyen içerik korunur. MCP'nin özgün `SYNTHETIC/0.0` deneyinde buton, sayı, kaynak içindeki boş sayfa ve nesne donor'ları, başlıklar, göstergeler, gezinme, bölüm sırası ve sınırlı internal makrolar işlenir. Konumu açık ayrı text sahibiyle birim üretimi ve kaynağa bağlı raw unit framing eklendi. Mevcut BOOL alarm metinleri ile kaynağın görünümü korunan hata şeridi, aktif tablo ve geçmiş nesneleri de dar bir dosya sözleşmesiyle işlenir. Embedded caption/conversion ayarları ayrı korunur. Font/renk düzeltmeleri native scalar sözleşmesidir; gerçek vendor piksel görünümü doğrulanmış değildir. Makro komut metniyle operand bağları birlikte üretilir; tam native sahibine, tetikleyiciye ve korunmuş zamanlamaya göre yeniden doğrulanır. Tam program üretimi kapalıdır; source-pinned mevcut literal-text/geometri aday yolu ve ayrı yeni literal-sayfa deneyi aşağıda tanımlanır. Haricî makro adresleri, yeni alarm tanımı/tetikleyicisi ve geçmiş saklama ayarları, tam görsel katman üretimi ve seçilmiş hedef kalibrasyonları henüz tamamlanmadı. İki aile için üretim/derleme/panel kabulü yoktur. [Alarm görünümü aşaması](reports/NATIVE_ALARM_VIEW_MILESTONE.json) · [birim aşaması](reports/NATIVE_UNIT_MILESTONE.json) · [layout aşaması](reports/NATIVE_LAYOUT_MILESTONE.json) · [makro/alarm aşaması](reports/NATIVE_MACRO_ALARM_MILESTONE.json) · [açık işler](reports/VERIFICATION.md).

Yeni geliştirme yolu, kaynak sayfanın yalnız başlığını ve boş Aux bölümünü alıp **yeni sayfalar ve Türkçe yazı nesneleri** üretir. Kaynaktaki bağlı sayı/işlev nesneleri yeni sayfaya kopyalanmaz. MCP akışı ayrı dosya kaydeder ve onaylı niyetle bütün ham gövdeyi karşılaştırır. Bu `literal_page_generation` dosya deneyi tam program yazarı değildir: komutlar, PLC adresleri ve gezinme bu yolda yoktur; bilinmeyen dosya bölümlerinin yeni sayfa/nesne sayısına bağımlılığı henüz doğrulanmamıştır. [Uygulanabilir adımlar](docs/LITERAL_PAGE_GENERATION.md) · [tam sınırlar ve test](reports/LITERAL_GENERATION_MILESTONE.json).

## Kurulum

Temiz RAR aktarımı için [paket başlangıcı](docs/CLEAN_PACKAGE.md) yeni Git baseline, kurulum ve host MCP ayarını açıklar. Kullanıcı projeleri ve bilgisayara özel bağlantı dosyaları genel pakette bulunmaz.

Komut/sayı/sürücü eşlemesi için [kaynak gözlem aracı](docs/CONTROL_CALIBRATION.md) eklendi. Yetkili `.dps/.dpa` kaynağının exact owner ve global alanlarını ölçer; açıklamalardan tür, adres varlığından yazma yetkisi üretmez. Bu araç tam program yazarı kabulü değildir.

0.2.0 kurulumu release ZIP üzerinden yapılır. Git veya önceden kurulmuş Python gerekmez; eksik Python sabit sürüm/hash ile proje klasörüne kurulur. Windows x64: `powershell -NoProfile -File scripts/setup.ps1`. Ubuntu x86_64: `sh scripts/setup.sh`. Çevrimdışı pakette Windows için `-Offline -ForceRuntime`, Linux için `--offline --force-runtime` kullanılır. macOS bu sürüm kabul hedefi değildir.

Kurulu profil/template kaynakları wheel içinden okunur. Yazılabilir çalışma alanı açık `--workspace` ile verilir; verilmezse mevcut çalışma dizininin `projects` klasörüdür. Kurulum ve istemci ayarları host'ta üretilir; eski kullanıcı/diske bağlanılmaz. Checkout geliştirme içindir, runtime kurulumu yayın ZIP'iyle yapılır. [Ayrıntılı taşınabilir kurulum](docs/HEADLESS_INSTALL.md).

## Yeni ajan görevi

**DOP-B için görev başlangıcı:** [DOP-B programlayıcı ajan talimatı](prompts/DOP_B_PROGRAMMER.md) ve [kaynağa bağlı aday rehberi](docs/NATIVE_CANDIDATES.md) hazırdır. Mevcut Type10/SubType6 sabit metin sahibinin caption/geometrisi kaynak, raw native sürüm ve kalibrasyon hash'ine bağlı ayrı `.dps` adaya yazılabilir. Diğer nesneler `native_preserved` olarak tam byte eşit tutulur. Bu dar yol yeni sayfa, buton, tag, sürücü, macro veya alarm üretmez; **sıfırdan tam program yazarı hâlâ tamamlanmadı**. Etkileşimli yolda exact insan onayı korunur. Headless yolda ayrı başlatıcı policy’sindeki görev başlangıç yetkisi ve exact bağımsız denetimler kullanılır; origin veya approval JSON’u kendi başına yetki değildir.

Yeni görevi bu repo klasöründe aç ve [başlangıç promptunu](prompts/START_NEW_PROJECT.md) kullan. Ajan [AGENTS](AGENTS.md), kanonik politika ve indeksi okuyarak başlar; task envelope/checkpoint hazırlar, rol ve kapsamı seçer. [Workflow](docs/WORKFLOW.md) ve [goals](docs/GOALS.md) aşama kabulünü belirler. Önizleme için iki sıralı bağımsız estetik denetmen, native üretim için ayrı teknik denetmen gerekir. Etkileşimli insan onayı veya kapsamı sabitlenmiş headless görev başlangıç yetkisi ilgili akışa göre uygulanır.

```powershell
.venv/Scripts/python.exe -m universal_hmi.cli new-project projects/ornek --id ornek --profile dop_b07s411_dopsoft2
```

Gerçek makine dosyaları, adres kaynağı ve insan kanıtları `projects/<id>/` içinde ayrı kalır. Test hedeflerini biz seçtik: **DOP-B07S411, 800×480** ve **DOP-110IS, 1024×600**. Bunlar evrensel çekirdeği tek modele bağlamaz. Yeni proje kendi profilini seçer; aile genelinde destek varsayılmaz.

## MCP

Yeni [DIAScreen maintained buton yolu](docs/DIASCREEN_BOUND_BUTTONS.md), sabitlenmiş kaynak ve AS adres sözleşmesinden ordinary `button` tanımını ayrı `.dpa` adaya yazar. Kalibrasyon aracı gerekli adres tablosunu çalışma klasörüne otomatik ekler; runtime'da eski bilgisayardaki dosyaya bağlanmaz. Bu kaynak programı koruyan dar dosya kabulüdür; temiz yeni program, seçilmiş DOP-110IS, native görünüm veya vendor/panel kabulü değildir.

Yeni [boş hedef üretimi](docs/BLANK_PROGRAM.md), referans kontrol kütüphanesini ayrı tutarak gerçek boş projeye yalnız tasarımın dört buton türünü ve UINT input/display nesnelerini yazar. Native dosya yeniden okunur ve bağımsız IR beklentisiyle karşılaştırılır. İsteğe bağlı [Delta DVP adres sözleşmesi](docs/DRIVER_ADDRESSES.md) ayrı M/S/D adreslerini kaynak sürücüsüne bağlar; UINT raw input korunur; ayrıca [explicit ondalıklı display](docs/FIXED_DECIMAL.md) source-qualified dar kapsamda açıldı. Tam program/derleme/panel kabulü açık kalır.

```powershell
.venv/Scripts/python.exe -m universal_hmi.cli --profiles profiles serve --workspace projects
```

Yeni [üç kaynaklı çok sayfa modu](docs/MULTIPAGE_PROGRAM.md), aynı B10 modelinden ayrı literal/gösterge/goto referansları kullanarak kontrolleri birden fazla ordinary sayfaya yerleştirir. Yardımcı dosyanın değişmiş driver/global verisi alınmaz. Gerçek9SDK dosyasında3sayfa/13owner ve bağımsız tam gövde eşitliği doğrulandı; [590kontrol](reports/MULTIPAGE_MILESTONE.json) stored-layout kapsamındadır. Diğer native veri türleri, tam görünüm/quality, macro/alarm/history birleşimi, DIAScreen gerçek kaynakları ve insan vendor/panel kabulü açık kalır. Önceki clean RAR bu geliştirmeyi içermez.

Varsayılan sunucu stdio üzerinden dokuz araç sunar; ayrı host policy/state ile beş headless job aracı daha açılır ([iş akışı](docs/HEADLESS_RELEASE.md)). Eski araçlar: `open_project`, `capabilities`, `inspect`, `plan_changes`, `preview`, `validate`, `apply_plan`, `save_as`, `diff`. [MCP istemci örneği](.mcp.json.example) makineye özel yol içermez; kurulu Python ortamını kullanır, repo varsayılanları istemcinin çalışma dizininden bağımsızdır. Bu dosya otomatik kayıt veya global ayar değişikliği yapmaz.

Codex için [TOML örneği](scripts/codex_config.toml.example) hazırdır. İlgili tablo kullanıcı veya güvenilen proje `config.toml` dosyasına aktarılır; örnek `command` ve `args` stdio ayarlarını kullanır. [OpenAI MCP rehberi](https://developers.openai.com/codex/mcp/). Bu repoda gerçek SDK istemcisiyle bağlantı test edildi; Codex'in global ayarı değiştirilmedi ve sunucu oraya otomatik kaydedilmedi.

Örnek ayarlar `python -m universal_hmi.cli serve` kullanır; paket bu Python ortamına kurulmuş olmalıdır. Yeni host'taki venv için `.venv/Scripts/python.exe scripts/configure_mcp.py --format codex` (POSIX: `.venv/bin/python`) o host'un bağlantı tablosunu üretir. Üretilen yollar host'a özeldir; örneği eski PC'den taşımak yerine yeni host'ta bu komut tekrar çalıştırılır. Config üreticisi istemci dosyasına yazmaz. `--workspace` ile ayrı makine çalışma alanı seçilebilir.

Kaynak yolu workspace'e göre relative olur. Oturum kaynağın SHA'sını dondurur; kaynak/profil değişirse işlem durur. Tekrar çağrı aynı işlemi çoğaltmaz. Kayıt yeni dosyaya atomik oluşturma ve yeniden okuma ile yapılır. `save_as` vendor derlemesi anlamına gelmez.

`plan_changes` çağrısında `operations` verilmezse onaylanacak değişiklikler ekran tanımından derlenir. Yeni nesne/sayfa için donor, yalnız açık oturumdaki sabit sayfa/nesne kimliğidir; başka makinenin dosya yolu değildir. Yeni sayfa, boş ve dar sözleşmesi doğrulanmış source-local donor gerektirir; eski arka plan, kilit veya makro taşınamaz. Yeniden adlandırma ve tam native kimlik sıralaması desteklenen bölüm dizisiyle yapılır; varsayılan yapısal yolda anlamı doğrulanmamış `Order` alanı no-op durumda da reddedilir. Ayrı source-pinned mevcut-nesne yolu ham `Order` ve bütün prefix baytlarını değiştirmeden tutar; bunlardan katman anlamı çıkarmaya izin vermez. Native katman/piksel kabulü açık kalır. Tip, adres, durum, font/renk encoding'i veya companion alan eşlemesi eksikse açık hata döner. Explicit planlar da temsil edilmeyen native özellikleri değiştiremez. [Mimari](docs/ARCHITECTURE.md).

Makro içeren sözleşme ayrıca `native_schema.macro_bindings` ile her IR kimliğini exact native owner/field/trigger/schedule değerlerine bağlar. Kaynağın kendi satır SHA'ları, bütün descriptor/flags ve internal adres aralığı kalibre edilir. UINT/UDINT/DINT atama, BOOL bit aç/kapat ve UINT eşitlik koşulu desteklenen dar alt kümedir; alias, external/DIA Tag, farklı tip veya farklı koşul sessizce dönüştürülmez. Clock süresi tahmin edilmez. Tasarımda belirtilmeyen makro ya da global kaynak değişimi, explicit planlarda da reddedilir.

Alarm IR'si `history_policy: "preserve_source"` ve source-local `native_schema.alarm_ir` ister. Yalnız mevcut, etkin, doğrudan active-high BOOL kayıtların birincil dil metni değişir; bütün etkin kayıtlar açık eşlenir. Adres, kanal/istasyon, bir bitlik saklama ve altı native companion alanı kaynak hash'iyle doğrulanır. Yeni kayıt/tetikleyici, continuous veya numeric alarm, biçimlendirme operandı ve history retain/clear ayarı üretilmez. Kaynakta görünüm sahipleri `native_schema.alarm_views` ile sabitlenir; `view_policy: "preserve_source"` nesnesinde yalnız kimlik ve geometri değişebilir. Sütun, dil, tarih/saat, font, State ve bilinmeyen görünüm alanları byte eşit korunur. Önizleme bu nesneleri açıkça native görünümü çizilmemiş UNKNOWN alan olarak gösterir; geçmiş verisi uydurmaz. Bu sözleşme kayıt korumasını doğrular, vendor davranışını değil. [Ayrıntılı sözleşme](docs/ARCHITECTURE.md).

## Önizleme ve destek

[800×480 örneği](examples/neutral_800x480.preview.html) · [1024×600 örneği](examples/neutral_1024x600.preview.html). Bunlar örnek değerli kavramsal tasarımlardır; native vendor katmanını veya canlı PLC'yi göstermez. Dış kontrollerle 0/1 ve geçersiz veri görünümü incelenir; HMI komutları çalıştırılmaz.

```powershell
.venv/Scripts/python.exe -m universal_hmi.cli preview examples/neutral_800x480.json synthetic_dopsoft2 projects/ornek/preview/R001.html
```

Registry gerçek profilleri `UNVERIFIED`, özgün deneyleri `SYNTHETIC_ONLY` tutar. Common IR özellik testleri native emit özelliği değildir. [Destek matrisi](docs/SUPPORT_MATRIX.md), [mimari](docs/ARCHITECTURE.md), [son teknik denetim](reports/FINAL_REVIEW.md) ve [insan kabul süreci](docs/HUMAN_HANDOFF.md) kapsamı açıklar.

Sıradaki çalışma: seçilmiş iki hedefin tarafsız vendor boş projesi ve nesne örneklerinden tam tip/görünüm/makro/alarm emitter'larını kalibre etmek; aynı tarafsız pilotu gerçek iki native dosyaya dönüştürmek. Vendor açma/kaydetme/derleme/simülasyon ve panel kabulü insanda kalır. Bu sürüm remote push veya panele yükleme yapmaz.

Birim yerleşiminde numeric `unit_label`, aynı sayfadaki ayrı text nesnesine bağlanır. Birim ve tag sözleşmesi exact eşleşir; konum, font ve renk açık belirtilir. Native embedded unit kapalı/boş kalır ve dönüşüm context byte’ları kaynak sahibiyle eşit korunur. `ShowUnit=0` tek başına değer dönüşümünü doğrulamaz. Low-level caption helper native konum veya vendor kabulü sayılmaz; public IR’ye ikinci caption yazma yetkisi vermez.

DOP-B ekran programı yazacak ajanın gerçek üretim durumu ve somut kalan adaptör işleri [DOP-B durum kaydındadır](reports/DOP_B_READINESS.md). Mevcut gerçek B örneğinin tek-record memory-only yazımı, MCP ile program teslim kabiliyetinin tamamlandığı anlamına gelmez.

Güncel [radix v2 adres sözleşmesi](docs/RADIX_ADDRESSES.md) sekizlik X/Y ile Read/ReadWrite yönünü ayrı registered authority üzerinden doğrular. Eski M/S/D profili değişmez; proje-local profil explicit upgrade ister. [604 testlik denetim](reports/RADIX_ADDRESS_MILESTONE.json) ve gerçek3sayfa/15owner aday offline dosya kanıtıdır; native piksel/runtime/vendor/iki aile tam kabulü açıktır.

[Ayrı INT16/F0 dönüşümü](docs/INT16_STORAGE.md) existingUINTsource/property kanıtını koruyarak fresh numeric cloneu signed yapar. Primary static authority/source/donor pin ve explicit opcode gerekir. [623-test denetim](reports/INT16_STORAGE_MILESTONE.json), gerçek3page/16owner dosya; signed donor/property bulunmadı ve nativepixel/vendor/iki aile tam kabulü açık.

## Public distribution

Version 0.2.1 licenses the original backend under [Apache-2.0](LICENSE). See [public release](docs/PUBLIC_RELEASE.md) and [third-party notices](THIRD_PARTY_NOTICES.md). This packaging release does not expand native, vendor or physical qualification.

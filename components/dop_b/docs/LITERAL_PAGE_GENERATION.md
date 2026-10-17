# Literal sayfa üretimi — deneysel offline native aday

`literal_page_generation`, kaynak projenin sonuna **yeni sayfalar ve yalnız sabit text nesneleri** ekleyen ayrı dosya modudur. DOP-B `.dps` ve DIAScreen/DOP-100 `.dpa` adaptörlerini kullanır; mevcut sayfa/kumandaları değiştirmez. Tam HMI program yazarı değildir: `program_writer_complete=false`; opak proje bağımlılıkları `UNKNOWN`, native görünüm/vendor/fiziksel kabul `NOT_RUN` kalır.

Bu belge giriş yolunu ve kapsamını anlatır; yeni test veya gerçek B kaynak PASS'ı ilan etmez. Exact revision/test/bağımsız inceleme ve varsa genuine public kaynakta memory-only gözlem root [doğrulama raporunda](../reports/VERIFICATION.md) ayrıca dondurulur. Public kaynak gözlemi vendor dosya/asset'ini repo'ya taşıma veya bütün modelleri kabul etme yetkisi değildir.

## Ayrı modlar

| Mod | İzinli niyet | Byte sınırı |
|---|---|---|
| `existing_owner_candidate` | Seçilmiş mevcut inert literal text caption/geometrisi; diğer kaynak içeriği korunur. | Mevcut caption/geometri extent'i değişmez. Değişmeyen numeric değer raw yazımı normalize etmez. [Ayrıntı](NATIVE_CANDIDATES.md). |
| `literal_page_generation` | Original graph aynen tutulur; sonuna yeni header-only sayfalar ve yeni sabit text owner'lar eklenir. | **Yeni bloklarda** native ID, geometri ve primary UTF-16 caption byte uzunluğu değişebilir. Original blocks byte-exact kalır. |

İki modu karıştırma. Generation modunda source text edit/delete/reorder veya button/numeric/indicator/goto, driver/adres/tag/macro/alarm/style emission yoktur.

## Kaynak ve donor

Yetkili native kaynak ve gerçek inventory gerekir. Örnekteki `inputs/blank.dps` yalnız dosya adıdır; helper sıfırdan vendor formatı kurmaz. Kaynakta uygun sayfa başlığı ve inert literal text donor bulunmalıdır. Text örneği olmayan boş projeyi kabul ettirmek için field veya donor uydurma.

Page donor'dan yalnız `[Screen]` başlığı ve hemen ardından gelen **boş `[AuxKeyElement]`** alınır. Donor sayfadaki numeric/function/command veya diğer owner blokları yeni sayfaya kopyalanmaz; source sayfasında byte-exact korunur. Yeni header'da yalnız native ID ve isim değişir; bütün diğer raw alanlar ve çözünürlük kaynaktan gelir.

Text donor immutable kaynaktaki full Element+tek State extent'idir: exact Type10/SubType6, primary State Value0, inert read/write/offset/visibility ve ayrı bounded raw companion gate gerekir. Aktif lock/macro/address/action, kalibre edilmemiş sound/picture veya unknown donor alanı salt SHA pinlenerek kabul edilemez. Missing/duplicate/unkeyed veya secondary caption varyantları da gate'ten geçmelidir. Donor pin'i font/picture/flag enum veya vendor davranışının feature calibration'ı değildir.

Yeni text'te yalnız nPartsID, X/Y/Width/Height ve primary wTextLen0 değişir; diğer bütün Element/State header ve record'ları donor ile aynıdır. Font/renk/hizalama gibi native sunum korunur; JSON style override eklenmez. Caption frame terminal NUL dahil doğru UTF-16LE uzunluğuyla yazılır; malformed surrogate/NUL/frame reddedilir.

## Taşınabilir giriş

[Kurulum](PORTABILITY.md), üç kontrol belgesi, rol/envelope/checkpoint okunur; resume/edit gate geçilir. Private girdiler, donor review ve onaylar ignored proje-local kalır. Core'a müşteri yolu/logo/tag veya lisansı belirsiz vendor asset taşınmaz. Provenance kaydı owner, kaynak edinimi ve kullanım/redistribution sınırını anlatır; public URL izin değildir.

Komutlar repo kökünden, bu checkout'a kurulmuş `python` interpreter'ıyla çalışır. `<project>` yetkili yerel workspace; `<SID>` ve `<SID/EID>` actual inspect kimlikleridir:

```text
python -m universal_hmi.cli inspect "<project>/inputs/blank.dps" --family delta_dopsoft2
python scripts/calibrate_source.py --workspace "<project>" --source "inputs/blank.dps" --family delta_dopsoft2 --output "revisions/R001" --mode literal_page_generation --page-donor "<SID>" --text-donor "<SID/EID>" --source-reference "<ownerref>" --review-reference "<reportref>"
```

Workspace/source önceden mevcut olmalıdır. Donor kimlikleri positive canonical source kimlikleridir; farklı kaynak sayfaları olabilir. Generation'a `--edit-text` eklenmez. Helper existing target'a yazmaz; yeni revision seçilir. Source/review referansları gerçek görev kayıtlarıdır; bu string'ler tek başına hak veya kabul kanıtı değildir.

Helper **yalnız üç JSON** üretir:

| Dosya | İçerik |
|---|---|
| `revisions/R001/CALIBRATION.json` | Source SHA/family/model/raw serialized Version/çözünürlük/schema SHA ve source/review/donor bağı. |
| `revisions/R001/profiles/literal_generation_v1.json` | Prefix/section SHA'ları, source page header+Aux/full text owner pin'leri ve workspace-relative calibration yolu/raw SHA. |
| `revisions/R001/design.json` | Bütün original sayfa/nesneler source sırasıyla korunmuş IR; henüz yeni sayfa yoktur. |

Sonuç `SOURCE_LOCAL_CONTRACTS_ONLY`, scope `APPEND_LITERAL_PAGES`, native_output `NOT_CREATED` olmalıdır. `qualified=true` veya donor pin'i vendor/execution kabulü değildir. DIAScreen için family `delta_diascreen`, source `inputs/blank.dpa` seçilir; uzantı değiştirmek family dönüşümü değildir. Raw Application.Version, bazı profile alanlarında editor_version adıyla taşınsa da executable build'i kanıtlamaz; build insan vendor kanıtında ayrıca kaydedilir.

MCP bu revision'ın ayrı registry/workspace'iyle başlar:

```text
python -m universal_hmi.cli --profiles "<project>/revisions/R001/profiles" serve --workspace "<project>"
```

Global `--profiles`, `serve` öncesindedir. Client interpreter/argümanları yeni host'ta çözülür; yazar PC yolu/eski `.venv`/config taşınmaz. Aynı literal_generation_v1 ID'si farklı registry'lerde başka kaynağa bağlıdır; registry/source eşlemesi korunur.

## Design'a append

Original sayfalar başta ve source sırasıyla kalır. Her source owner exact native_preserved kaydıyla tutulur: native ID, full Element+States SHA, source geometry ve boş text. Yeni text'e dönüştürme/hash değişikliği/edit/delete/reorder yoktur. Top-level tags/macros/alarms boş kalır; source resources silinmez.

Yeni page tam altı alan taşır: `id`, `native_id`, `name`, `width`, `height`, `elements`. Width/height exact profile çözünürlüğüdür; name açık/nonempty ve CR/LF/NUL'sızdır. Native page ID, source pages ile çakışmayan positive canonical decimal string, en çok 2147483647 olur; sıfır/leading zero/reuse yoktur. Source'un sonuna eklenir. `elements=[]` header-only empty page'dir; source object'leri miras almaz.

Yeni text tam sekiz alan taşır: `id`, `native_id`, `kind`, `x`, `y`, `width`, `height`, `text`; kind text'tir. Yeni native element ID **project-wide fresh** olmalı: bütün source/new pages owner'larından farklı positive canonical decimal string. IR logical IDs de tekrarsız olur. X/Y nonnegative integer, width/height positive integer ve source çözünürlüğü içinde kalır. Font/color/fill/style, binding, State listesi, behavior/unit/numeric/action eklenmez. Variable byte extents yalnız yeni managed ID/geometri/primary caption kayıtları içindir.

## Dokuz araç ve kabul kapıları

| MCP | Kullanım |
|---|---|
| open_project | profile_id literal_generation_v1, source_path inputs/blank.dps; actual source/calibration session. |
| capabilities | Dar scope/UNVERIFIED/vendor sınırını oku. |
| inspect | Actual source/donor/page/ID envanteri; yeni ID ayır. |
| plan_changes | Tam retained+appended design, yeni idempotency key; operations omitted/null. |
| preview | Yeni revisions/R001/preview.html; conceptual text/coordinate intent. |
| validate | Source freshness, immutable donor/graph, append/ID/geometry/frame ve exact operations. Findings kapanmadan apply yoktur. |
| apply_plan | Exact session/plan ve gerçek insan approval dosyası; yalnız bellekte. |
| save_as | Yeni revisions/R001/candidate.dps veya doğru .dpa; atomic new-only kayıt, reopen/whole-byte hedef kontrolü. |
| diff | Source/candidate SHA, kontrollü işlemler, reopened inventory; çalışabilirlik hükmü yoktur. |

Teknik denetmen read-only çalışır. Estetik iki uzman sıralı inceler; ikinci ilk raporu ve uygulayıcıyı da eleştirir. Bir odaklı estetik düzeltme/tekrar inceleme sonrası önemli açık kalırsa tasarım teslimi STOP; fonksiyonel hatada kabul kapanana kadar düzeltme sürer.

Preview `CONCEPTUAL_IR / TEXT INTENT ONLY`'dır. Browser font/color/fill/fit donor görünümünü çizmez; retained unknown owner SOURCE OBJECT / NATIVE NOT RENDERED placeholder'ıdır. İnsan metin/koordinat niyetini onaylar; native glyph/pixel/vendor görünümü ayrıca kullanıcıda sınanır. Eski preview veya agent consensus onay değildir.

Approval plan receipt'indeki exact source_sha256, profile_sha256, design_sha256, bindings_sha256, operations_sha256, calibration_sha256 ve approved=true/authority=direct_human/gerçek human_reference taşır. Mode/donor/schema kapsamı profile/calibration hash bağına dahildir. Bunlardan biri değişirse eski onay geçersizdir. Neutral istisnası actual SYNTHETIC/0.0 + synthetic profile + qualification_only içindir; origin etiketi vendor kaynağına yetki vermez. İnsan onayı uydurulmaz.

## Dosya kanıtı ve açık kabul

Değişmiş native body gzip olarak yeniden üretilir ve kayıt yeniden okunur. BMP/thumbnail, envelope prefix, global prefix, opaque tail ve original page/owner blokları korunur. New blocks'ta managed ID/name/geometri/primary caption dışındaki header/State records source donor ile aynıdır. Pure verifier, operation setter'ından ayrı immutable source + onaylı IR'dan tam decoded expected payload oluşturur. Empty append whole-file byte no-op'u korur.

Thumbnail'ın korunması yeni sayfaların render edildiği anlamına gelmez. SHA/frame/gzip/reopen kontrolleri opak metadata'nın yeni page/owner sayılarına bağımlı olmadığını kanıtlamaz. Bu graph dependencies **UNKNOWN** kalır; çıktı **deneysel OFFLINE_NATIVE_CANDIDATE**'dır, vendor-valid/executable/panel-ready diye sunulmaz.

Kullanıcı doğru vendor executable'ında ayrı adayı açar/kaydeder/derler ve görünümü inceler; simulation/panel/PLC ayrıca insan kabulüdür. Vendor save yeni SHA üretirse yeniden inspect/diff/kanıt eşlemesi gerekir. Ajan GUI/IDE/PLC/download yapmaz.

Teslim source SHA/provenance, üç sözleşme, retained+appended design, plan/preview/teknik ve iki estetik rapor, gerçek approval, apply/save/diff receipt'leri ve candidate SHA taşır. Helper JSON çıktısı native teslim değildir. Genuine B07E515 public memory-only örneği varsa exact source/model/revision ve izin sınırı root raporunda ayrı kalır; reusable belgeye asset veya kişisel path alınmaz.

Tam V1 açık: actual selected model/driver, command/button/numeric/mod/feedback, yeni tag/adres/macro/alarm/history, font/style/picture/layer/unit/conversion, iki gerçek ortak pilot G4, insan vendor G5 ve panel G7. Yeni revision final bağımsız test/fresh ortam/manifest/scoped commit ister. [Goals](GOALS.md)/[destek matrisi](SUPPORT_MATRIX.md) okunur; FrameworkReady veya literal page dosyası full program writer değildir. [Ajan başlangıcı](../prompts/DOP_B_PROGRAMMER.md), [Kaizen](../kaizen/LITERAL_PAGE_GENERATION.md).

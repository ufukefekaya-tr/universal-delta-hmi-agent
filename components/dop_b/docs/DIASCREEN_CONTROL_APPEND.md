# DIAScreen — mevcut kaynaktan kontrol klonlama

Bu ayrı sözleşme, mevcut `.dpa` kaynağındaki dört kontrolün yeni kopyalarını oluşturur. Yalnız yeni ID, geometri ve butonların primary 0/1 yazıları değişir. Bütün kaynak nesneleri, adresler, sayısal ayarlar, stiller, makrolar ve bilinmeyen kayıtlar korunur. Güncel kabul ve test revision'ı [doğrulama raporundan](../reports/VERIFICATION.md) okunmalıdır; bu belge tek başına kabul kanıtı değildir.

## Exact hedef

`diascreen_control_append` public modu, `diascreen_source_control_append_v1` native descriptor'ına bağlıdır. Gözlenen hedef `delta_diascreen`, model `268502784`, serialized `6.0.00205.8268`, ana canvas `800×480`'dir. Bu, kaynak dosyasının kimliğidir; kurulu editor sürümü, bütün DOP-100 ailesi veya seçilmiş DOP-110IS kabulü değildir.

Geliştirme kaynağı kurulu üretici `Full_Element_Demo.dpa` örneğidir; SHA `fc079f74ed9b34e2e698b0c65c95c4f914983594f658cadc72e1ee4d97493ed5`. Dosya genel repo/paket içinde bulunmaz. Kaynak 18 sayfa ve 648 owner içerir. Page24'ün Doc canvas'ı `126×96`, Panel canvas'ı `800×480`'dir; bu değerler ayrı ayrı korunur. Yeni nesneler yalnız page20'ye eklenir. Bu sayfanın 26 eski owner'ı, başlığı, Aux extent'i, `EnableCycleMacro=1`, `ScreenAction=18` ve sıfır uzunluklu üç makrosu korunur.

| Donör | Page/ID | Aynen korunan alanlar |
|---|---|---|
| Maintained | 5/66 | Type1/Sub4; Write `$430.0`; Read `None`; BOOL 0/2 |
| Momentary | 13/3 | Type1/Sub3; Write `$2.1`; Read `None`; BOOL 0/2 |
| Sayısal giriş | 2/19 | Type6/Sub1; Write `$120`; Read `None`, ReadMemType3; UINT WORD; 0..100, I3/F0 |
| Sayısal gösterge | 6/10 | Type5/Sub1; Read `$510`; Write `None`; UINT WORD; I4/F0 |

Momentary donörünün `TransEffect1/StretchMode2/PictureStretch1` değerleri korunur; efektlerin etkin olmadığı veya render-safe olduğu iddia edilmez. Girişin 0..100 baseline'ı bütün UINT domain'inin sığması anlamına gelmez. Yeni ID'ler 97..100'dür; var olan bütün ID'lerle çakışma kontrol edilir. 21 global prefix bölümünün tam byte sırası, resource tail, thumbnail ve dış prefix korunur; yalnız gerekli declared BODY uzunluğu onarılır.

## Doğru ortak model

Yeni nesne `native_control_clone` olarak tanımlanır. Exact alanlar: `id`, `native_id`, `kind`, `x`, `y`, `width`, `height`, boş `text`, donörün tam `source_owner_sha256` değeri ve `clone`.

`clone`, yalnız `donor_kind` ve `captions` içerir. Butonlar ordered `{value:0,text:...}` ve `{value:1,text:...}` ister; sayısal kopyalar boş caption dizisi ister. Yeni binding, tag, behavior, sample, numeric limit/format, stil, unit veya makro intent'i kabul edilmez. Donörün Type/SubType alanı etiketten türetilmez veya değiştirilmez.

Bu ayrı capability, genel `button`/`numeric_input`/`numeric_display` veya yeni program üretimi kabulünün yerine geçmez. Girişte olmayan ReadVar'ı tahmini read tagına çevirmek mantıksal bir bağı uydururdu. Önizleme bu yüzden `SOURCE CLONE / UNKNOWN / NATIVE NOT RENDERED` placeholder'ını gösterir; canlı değer, runtime durumu veya native font/pixel görünümü göstermez. MCP preview çağrısında sample/state parametreleri reddedilir.

## Yerel ve taşınabilir akış

Kaynak ve bağımsız kaynak incelemesi göreve ait ignored workspace içinde bulunur. Kaynak incelemesinin JSON kaydı; exact kaynak SHA, model/sürüm, dört donörün page/ID/raw owner SHA değerleri ve review referansını taşır. SHA eşitliği, bir incelemenin gerçekten yapıldığını veya dosyanın yeniden dağıtım lisansını kendiliğinden kanıtlamaz.

```text
python scripts/calibrate_diascreen_controls.py --workspace "projects/<project-id>" --source "inputs/source.dpa" --output "contracts/v001" --origin manufacturer_installed_example --source-reference "inputs/PROVENANCE.md" --review-reference "reviews/source.md" --review-artifact "reviews/source_review.json"
```

Helper native çıktı üretmez; kaynak, ayrı review artifact'i ve kaynak SHA'sına bağlı `CALIBRATION.json`, ayrı profil registry'si ve bütün eski owner'ları koruyan design oluşturur. Makine kaynağı için origin `user_vendor_project` olmalıdır. Review artifact ve calibration değişirse oturum durur. `.mcp.json` yeni host'ta bu registry/workspace yollarıyla üretilir; core içinde üreticinin kurulum yolu veya geliştiricinin PC yolu yoktur.

Design'a dört yeni clone intent'i eklendikten sonra [dokuz araç akışı](NATIVE_CANDIDATES.md) kullanılır. Onay source/profile/calibration/design/binding/operation hash'lerine bağlıdır. Üretici örneği sentetik approval istisnası kullanamaz. Tarafsız adaptör geliştirme için kullanıcının V1 yetkisi, müşteri üretim tasarım onayının yerine geçirilmez. `save_as` yalnız yeni `.dpa` dosyası oluşturur; kaynağın üzerine yazmaz.

## Koruma ve kabul sınırı

Emitter, immutable donörden klon üretir. Ayrı raw-record insertion oracle'ı tam beklenen BODY'yi kurar. Yeni owner blokları kaldırıldığında bütün kaynak BODY'nin byte eşitliği, saved reparse, deterministic replay, exact file no-op ve kaynak değişmezliği sınanır. Eski bir owner veya resource değişikliği, yalnız semantic inventory eşitliğiyle gizlenemez.

Yeni nesneler **eski adresleri bilinçli olarak paylaşır**. Kaynak boş makine projesi değildir: InitialMacro 6478 byte ve toplam 62 etkin makro bulunur. `$120` bir eski OpenMacro'da, `$510` bir eski CycleMacro'da kullanılır; yeni kopyanın değeri bu makrolardan etkilenebilir. Fresh-memory veya çakışmasız adres ayırma desteği açık kalır.

Set-on/set-off dönüşümü, yeni adres/sürücü, blank program, resource pointer semantiği, native çizim, IDE açma/kaydetme/derleme, runtime ve panel kabulü bu sözleşmeyle kapanmaz. Derleme ve fiziksel test insan tarafından exact aday SHA'sına bağlanır. Computer Use, IDE otomasyonu, PLC bağlantısı veya panele yükleme yapılmaz.

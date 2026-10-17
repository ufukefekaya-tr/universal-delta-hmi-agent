# DIAScreen: opak kaynak üzerinde dar düzenleme

Bu ayrı opt-in sözleşme, mevcut DOP-100 `.dpa` kaynağındaki **inert literal başlık ve geometri** kayıtlarını düzenler. Opak global kayıtları yorumlamaz; ham byte'larını ve sıralarını korur. Yeni kontrol, sayfa, adres, sürücü, macro veya alarm üretmez. Kabul sonucu ve exact test revision'ı [güncel doğrulamadan](../reports/VERIFICATION.md) okunur.

## Hedef ve kaynak sınırı

V2 `preserved_layout`, yalnız `delta_diascreen`, `PanelSeries=DOP-100 series`, native model `268502784`, serialized `6.0.00209.8338` ve bütün sayfalarda `800×480` için ayrılmıştır. Bunlar gözlenen dosya kimlikleridir; çalıştırılmış editor build'i veya aynı modelin bütün dosyalarının qualification'ı değildir. Seçilmiş DOP-110IS kabulü açık kalır. Her yeni kaynak SHA'sı için yeniden kaynak incelemesi, kalibrasyon ve uygun onay gerekir.

22 prefix bölümünün isim ve sırası sabittir. Tam prefix ve her bölüm SHA ile kaynağa bağlanır. Nonempty unkeyed kayıtlar yalnız `Ethernet`, `WEB_OUTPUT`, `LuaData` içinde opak tutulabilir; diğer bölümlerde bu biçim reddedilir. Kamera, Lua ve diğer global davranışların anlamı `UNKNOWN` kalır. Yeni bölüm, tekrar eden bölüm veya değişen prefix kabul edilmez.

V1'in eski kapalı parser sözleşmesi korunur. V2 yeni generation, blank/multipage compiler, `existing_edit` veya başka bir mutation şemasıyla birleştirilemez; işlemsiz çağrıda da karışık şema reddedilir.

## Değişiklik sınırı

Kaynak owner `Type10/SubType6`, tek `State Value0`, Read/Write/offset/visibility `None` ve boş Element/State macro koşullarını sağlamalıdır. Başlık seçimi yalnız state0/language0'dır. `X/Y/Width/Height` Element tamsayılarıdır. Her caption UTF-16 extent'i ve her ASCII geometry extent'i ayrı ayrı aynı uzunlukta kalır; iki alanın birbirinin uzunluk farkını telafi etmesi kabul edilmez.

Native doğrulayıcı yalnız izinli kaynak kayıtlarını geri koyup **tam decoded BODY**'yi kaynakla karşılaştırır. Public service, tasarımdan beklediği tam BODY'yi ayrıca kurar. Bütün diğer owner/state/page/global/resource/tail byte'ları korunur. Bu iki kontrol, bilinen sıranın korunmasıyla yetinmez; ilgisiz alan bozulmasını da yakalar. Başlık/geometri, font/renk/layer/driver semantiğinin doğrulandığı anlamına gelmez.

## Taşınabilir yerel kullanım

Yetkili kaynağı göreve ait ignored workspace'e getir. Makine yolu veya vendor kurulumu core'a bağlanmaz. Repo kökünden:

```text
python scripts/calibrate_source.py --workspace "projects/<project-id>" --source "inputs/source.dpa" --family delta_diascreen --output "contracts/v001" --edit-text "<screen-id>/<element-id>" --prefix-policy diascreen_opaque_source_v1 --origin manufacturer_installed_example --source-reference "inputs/PROVENANCE.md" --review-reference "reviews/source.md"
```

`manufacturer_installed_example` yalnız bu V2 existing-owner yoluna aittir; manufacturer kökeni etiketi tek başına provenance ispatı veya yeniden dağıtım hakkı değildir. Kullanıcı kaynağında `--origin user_vendor_project` seçilir. Vendor örneği repo, paket, fixture veya RAR içine alınmaz. Kalibrasyon kendi sözleşmesinin hash tutarlılığını kanıtlar; dosyanın üreticisini kendiliğinden ispatlamaz.

Ardından [dokuz araç akışı](NATIVE_CANDIDATES.md) uygulanır. Source/profile/calibration/design/binding/operation hash'leri onaya bağlanır. Gerçek vendor örneğinde sentetik approval istisnası kapalıdır. Genel V1 planının tarafsız adaptör test yetkisi yalnız bu geliştirme deneyi için kayıtlanabilir; müşteri üretim tasarımının onayı yerine geçmez.

## Kanıt ve açık işler

İlk gerçek holdout, üreticinin kurulu `Temperature_Control_Demo.dpa` örneğidir: kaynak SHA `b60f24b99cbee35adb8f84e8de18de227ffcaa58ac25d17b2e41f95c27a52baf`, bir sayfa (ID2), 26 owner. `2/4` başlığı `Control Mode → Control View`, X `93 → 94` seçilmiştir. Lisanslı dosya genel repo'ya eklenmez; yalnız alias/hash ve deney sonucu kaydedilir.

Dokuz stdio MCP aracı, kaydet/reopen, tekrar oynatma, kaynak restorasyonu ve bağımsız whole-BODY karşılaştırması exact aday SHA'sına bağlıdır. [Milestone](../reports/DIASCREEN_EXISTING_CANDIDATE_MILESTONE.json), [SDK kanıtı](../reports/DIASCREEN_EXISTING_CANDIDATE_SDK_PROOF.json), [bağımsız inceleme](../reports/DIASCREEN_EXISTING_CANDIDATE_REVIEW.md) sonuçları ayrı kayıtlanır. Kaynak envanteri yalnız framing/no-op gözlemidir; diğer örnekler bu adayın kabulüne taşınmaz.

Önizleme `CONCEPTUAL_IR`'dır. Native pixel, IDE açma/kaydetme/derleme, runtime, driver ve fiziksel panel testleri `NOT_RUN` kalır. `program_writer_complete`, `BothFamiliesVendorQualified`, `OperationalBothFamiliesComplete`, full V1 ve tam presentation batch bu dar deneyle kapanmaz.

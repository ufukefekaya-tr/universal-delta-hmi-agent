# V2 — adres tabanı ve işlem yönü

Bu sözleşme mevcut onluk v1'i değiştirmeden, kaynakla doğrulanmış Delta DVP serial X/Y bit adreslerini açar. `contract_version:2 / mode:source_driver_radix_regions` ayrı profile/authority ister. Runtime dosya MCP'si vendor DLL'ini yüklemez veya PLC'ye bağlanmaz.

## Alanlar ve kanıt

| Tip | Alan | Saklanan index sınırı | Native yazım tabanı | Normal işlem erişimi |
|---|---|---|---|---|
| BOOL | X | 0–255 | 8: X0–X377 | Read |
| BOOL | Y | 0–255 | 8: Y0–Y377 | ReadWrite |
| BOOL | M | 0–4095 | 10 | ReadWrite |
| BOOL | S | 0–1023 | 10 | ReadWrite |
| UINT | D | 0–11999 | 10 | ReadWrite |

X10/Y10 index8'dir;77→100 geçişi63→64 anlamına gelir. Canonical yazım uppercase alan ve baştaki gereksiz sıfırı olmayan native rakamlardır. X8/Y9, Y18, Y400, X01, artı/eksi/boşluk/lowercase/Unicode-digit/bit-suffix reddedilir. V1'in M10/D10 anlamı onluk10 kalır. Vendor alternatif yazımlarını reddediyor iddiası yoktur; kabul edilen alt küme nettir.

PE32 driver SHAe14767083390e1d35dbb8d9312d142d83491e75abcf68cd2b42fe807fddd9e72. X0xc250/Y0xc264 kayıtları inclusive0..255 ve radix8 verir. GetAddrValue radix'i yükleyip index'i8 ile biriktirir; validator yalnız0..7 rakamlarını alır. Direction bu DLL bit/word seçicisinden çıkarılmadı. X'in discrete-input, Y'nin coil olması ve normal read/write politikası [Delta cihaz haritası](https://filecenter.deltaww.com/Products/download/06/060301/Manual/DELTA_IA-PLC_DVP-PLC_PM_EN_20220407.pdf) ile [Delta Modbus erişim tanımlarına](https://filecenter.deltaww.com/Products/download/06/060308/Manual/DELTA_IA-IES_DX-2100RW-WW_UM_EN_20200525.pdf) dayanır. Resmi indekslenmiş bölümler incelendi; doğrudan PDF isteği terms/error döndürdü, downloaded-PDF hash veya tam PDF incelemesi iddia edilmez. Ayrı force/debug mekanizmaları bu politika dışındadır.

Sınırlar driver sözdizimidir. CPU'da o giriş/çıkışın varlığı, fiziksel feedback ve yetki ayrıca doğrulanır. Kullanıcının tag kataloğu daha dar olabilir. X tag'ına yanlışlıkla ReadWrite yazılması native X write'ı açmaz; Y tag'ı Read ise yazma yine yasaktır. UI'deki gösterge yalnız ReadVar kullanır; komut butonu fiziksel feedback olduğunu iddia edemez.

## Hazırlık

Orijinal altı kontrol profiliyle veya doğrulanmış v1 namespace profiliyle başlayabilirsin. V1→v2 yükseltme explicit authority seçimidir; v2→v1 downgrade veya zaten v2 profilin üzerine değiştirme reddedilir. Yeni output-dir gerekir.

```text
python scripts/calibrate_dvp_namespace.py --workspace "projects/<project>" --source "library/controls.dps" --library-profile "contracts/dvp-v1/profiles/source_controls_dvp_v1.json" --output-dir "contracts/dvp-v2" --review-reference "reviews/radix.md" --authority delta_dvp_serial_radix_2016.json
```

Çıktı yalnız calibration JSON ve `source_controls_dvp_v2.json`'dır. [Boş hedef](BLANK_PROGRAM.md) veya [çok sayfa](MULTIPAGE_PROGRAM.md) yardımcıları bu profili kendi exact target/library sözleşmesine taşır. Eski cached profile/approval yeniden kullanılamaz; server yeni registry ile yeniden başlatılır. Varsayılan authority seçiminde v1 davranışı aynıdır.

V2 region exact alanları `area,minimum,maximum,radix,access`'tir; radix8/10 ve accessRead/ReadWrite dışında değer alınmaz. Alan içindeki mixed radix, overlapping bölge, yanlış tip/derinlik/kaynak/driver/hash reddedilir. `match(...,direction)` gerçek read/write yönünü native source/candidate/bind ve service IR yolunda kontrol eder. Read-only policy source korunurken de geçerlidir; yalnız emitter sırasında kontrol edilmesi yeterli değildir.

[Yeni tarafsız authority](../profiles/driver_contracts/delta_dvp_serial_radix_2016.json) model/editor kaynak driver span ve original prefix/link/station bilgilerini ayrıca bağlar. DLL içindeki type128/129, DPS MemType alanına kopyalanmaz; original native MemType0 ve ReadLink1 korunur. V1 authority dosyası byte exact kalır. Helper yükseltme sırasında eski ve yeni registry/property/source dependency'lerini ayrı doğrular.

## Kayıt ve kabul

Gerçek B10 tarafsız örnek15owner/3pages, readonly X377/Y10/Y377 indicator'larıyla9SDK üzerinden ayrı DPS'ye kaydedildi. Bütün source/globals/BMP/ilk sayfa/Aux/unknown resource korunur; source byte'ları değişmez. Onaylı IR'nin bütün body beklentisi, saved file ve bağımsız yeniden üretim birlikte sınanır. X write, geçersiz octal, rehashed range/access drift, registry/source freshness ve eski v1 kullanımı negatif testtir.

Kabul **OFFLINE_DRIVER_SYNTAX_ONLY / OFFLINE_NATIVE_CANDIDATE**. Native style/font/pixels, gerçek PLC/communication loss, vendor compile/keypad/simulation ve fiziksel panel kabulü ayrı kalır. Signed/floating/diğer width/word spans bu namespace ile açılmaz; sürücünün span kontrolü native storage enum kanıtı değildir. [Milestone](../reports/RADIX_ADDRESS_MILESTONE.json), [probe](../reports/RADIX_ADDRESS_GENUINE_PROBE.json), [denetim](../reports/RADIX_ADDRESS_REVIEW.md).

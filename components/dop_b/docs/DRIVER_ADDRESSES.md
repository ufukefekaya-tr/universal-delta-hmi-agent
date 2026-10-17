# Kaynak sürücüsüne bağlı ayrı adresler

Bu katman dört buton türü ve UINT giriş/gösterge nesneleri için ayrı PLC adresleri üretir. `control_generation` ve `blank_program` aynı sözleşmeyi kullanır. Kaynak sürücüsü, haberleşme ayarları ve native saklama tipi değiştirilmez.

## Doğrulanan adres alt kümesi

Delta DVP serial sürücüsü, DOPSoft 2 kaynak profili ve raw serialized Version `4.00.07.04` için:

| Tip | Alan | Kapsayıcı sınır |
|---|---|---|
| BOOL | M | 0–4095 |
| BOOL | S | 0–1023 |
| UINT / 16-bit | D | 0–11999 |

Canonical kabul edilen biçim `{Link…}<station>@<area><decimal-index>`'tir; baştaki gereksiz sıfır, eksi, bit suffix, boşluk ve farklı alan reddedilir. Bu sistemin kabul ettiği alt kümedir; vendor bütün bu yazımları reddediyor iddiası değildir. Kaynakta kanal ve istasyon neyse aynen korunur. Örneğin kaynak etiketi Link2 iken native ReadLink/WriteLink alanı 1 olabilir; bu iki değeri eşitlemek yanlış olur. Driver DLL içindeki device kodları native MemType alanına yazılmaz.

Sınırlar sürücünün statik sözdizimi sınırlarıdır. Seçilen PLC CPU'sunun adres varlığı yetkili proje veya insan tarafından ayrıca doğrulanmalıdır; core CPU belleğini otomatik keşfetmez. Yetkili tag kataloğu, Read/ReadWrite hakkı ve kullanıcı onayı ayrı kapılardır. Word-M/S, D bitleri, diğer bellek alanları, width/signed/floating/TIME ve farklı sürücüler bu kabulden destek kazanmaz.

## Taşınabilir hazırlık

Önce altı vendor kontrolünü ve property kanıtını [kontrol kütüphanesi](CONTROL_GENERATION.md) ile kalibre et. Ardından:

```text
python scripts/calibrate_dvp_namespace.py --workspace "projects/<project>" --source "library/controls.dps" --library-profile "contracts/controls-v001/profiles/source_controls_v1.json" --output-dir "contracts/dvp-v001" --review-reference "reviews/driver-addresses.md"
python scripts/calibrate_program.py --workspace "projects/<project>" --target "inputs/blank.dps" --library "library/controls.dps" --library-profile "contracts/dvp-v001/profiles/source_controls_dvp_v1.json" --output-dir "contracts/program-v002" --source-reference "inputs/PROVENANCE.md" --review-reference "reviews/blank-lineage.md"
python -m universal_hmi.cli --profiles "projects/<project>/contracts/program-v002/profiles" serve --workspace "projects/<project>"
```

İlk komut yalnız yeni `control_calibration.json` ve `source_controls_dvp_v1.json` üretir. Kaynağa veya native projeye yazmaz. İkinci komut namespace'i ayrı boş hedef profiline taşır; yeni-only çıktı ve tasarım onayı kuralları değişmez. Append modu için doğrudan ilk komutun profile klasörü seçilebilir.

Core [profiles/driver_contracts/delta_dvp_serial_2016.json](../profiles/driver_contracts/delta_dvp_serial_2016.json) içinde yalnız tarafsız driver gerçekleri, kaynak hash'leri ve üretici referansı tutar. Runtime vendor DLL, program kurulumu veya yazarın disk yolunu istemez. Namespace tam kaynak driver span SHA'sına, kaynağın model/sürümüne ve kayıtlı authority dosyası SHA'sına bağlıdır. Proje kendi `qualified=true` veya yeniden hash edilmiş geniş range yazarak registered authority'yi aşamaz.

Plan, apply, inspect, validate ve save işlemlerinde kayıtlı sözleşme yeniden kontrol edilir. Kayıt sırasında kaybolan/değişen kaynak `CALIBRATION_CHANGED` verir; geçici çıktı temizlenir. Metadata kök tipi, derinliği ve düğüm sayısı kopyalamadan önce sınanır; malformed girdiler ham Python exception'ıyla geçiş yapmaz.

## Kanıt sınırı

Gerçek B10S615 boş hedefte M1/M10/S2/M4095/D10000/D11999 adresli altı nesne dokuz MCP aracıyla kaydedilip yeniden okunmuştur. Kaynak, driver, thumbnail, sayfa header/Aux ve kaynakta bulunmayan nesneler korunur; donor kütüphanesi çıktıya taşınmaz. [Araştırma](../reports/DRIVER_ADDRESS_RESEARCH.md), [gerçek dosya](../reports/DRIVER_ADDRESS_GENUINE_PROBE.json), [bağımsız denetim](../reports/DRIVER_ADDRESS_REVIEW.md).

Kabul `OFFLINE_DRIVER_SYNTAX_ONLY / OFFLINE_NATIVE_CANDIDATE`'dır. Native piksel, vendor derleme/simülasyon, keypad/PLC haberleşmesi ve panel davranışı `NOT_RUN` kalır. `program_writer_complete=false`; adres katmanı tam V1 veya iki model kabulünün yerine geçmez.

Bu belge original onluk v1'i tanımlar. X/Y için ayrı [v2 radix/direction sözleşmesi](RADIX_ADDRESSES.md) ve `--authority delta_dvp_serial_radix_2016.json` seçimi gerekir. V1 dosyası, mevcut profile veya onayı sessiz genişletilmez. V2 X/Y0–377 sekizlik ve normal XRead/YReadWrite politikasını kaynak driver/schema'ya bağlar; native storage/link alanları değiştirilmez.

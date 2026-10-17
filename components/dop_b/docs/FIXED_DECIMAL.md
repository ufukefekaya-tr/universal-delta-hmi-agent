# Ham tamsayı ve ondalıklı gösterim

`value_model: "integer_fixed_decimal"` açık seçilen bir sayı sözleşmesidir. Tag, `minimum`, `maximum` ve önizleme örnekleri ham tamsayı olarak kalır; ortak IR nesnesindeki `fractional` değeri gösterilecek ondalık konumunu belirler. Adaptörün `configure_numeric` işleminde aynı niyet `fractional_digits` alanıyla taşınır; bu alan IR nesnesine yazılmaz. Örneğin raw123/F2, `1.23`; aynı tag raw123/F1, `12.3` gösterir. Eski, belirtilmemiş/raw modelin anlamı değişmez.

Ortak model INT/UINT/DINT/UDINT için F0–15'i exact tamsayı/metin hesabıyla temsil eder. Görünen metni ham değere dönüştürme yardımcı işlevi yalnız exact grid'i kabul eder; yuvarlama, epsilon, float daraltma veya TIME yerine başka tip kullanma yoktur. Bu ortak matematik, vendor giriş desteği değildir. Stale/invalid/missing ya da ham saklama/işlem sınırı dışındaki örnekler `UNKNOWN` kalır. Önizlemenin dış örnek kontrolleri ham değer bekler.

## Kaynakla kalibre edilmiş native alt küme

Şimdiki gerçek adaptör yolu **DOP-B10S615 / raw serialized4.00.07.04 / UINT numeric display** için saklanmış ayardır. Model, kaynak/library SHA, MemLen1/MemFmt2, identity Gain1/Offset0, registered numeric authority SHA ve kaynak property witness ayrı ayrı doğrulanır. F0–4, I≥1 ve I+F≤5 gerekir. Göstergeye MinValue/MaxValue giriş alanları eklenmez. Signed/floating/TIME veya farklı hedefe bu kabul taşınmaz.

`profiles/numeric_contracts/dopsoft2_b10_uint_presentation.json` tarafsız statik sözleşme taşır; vendor DLL/program veya kurulum yolu runtime bağımlılığı değildir. Kaynak, profil, calibration, property ya da registered sözleşme değişirse oturum/kayıt durur. Genişletilmiş JSON'a yeni SHA yazmak yetki üretmez.

Önce [kontrol library'si](CONTROL_GENERATION.md) kalibre edilir. Ardından yalnız yeni profil/calibration JSON üret:

```powershell
.venv/Scripts/python.exe scripts/calibrate_fixed_decimal.py --workspace projects/ornek --source inputs/controls.dps --library-profile calibration/profiles/source_controls_v1.json --output-dir fixed/R001 --review-reference "Proje teknik denetimi R001"
```

Çıkan `source_controls_fixed_decimal_v1` profilini [blank hedef helper'ına](BLANK_PROGRAM.md) ver. Kullanıcının makine native adayı için tasarım, hedef ve binding/behavior sürümüne bağlı insan onayı yine gerekir. Helper kaynak dosyasını değiştirmez; native aday yalnız normal dokuz MCP aracı ve yeni `save_as` yoluyla üretilir.

## Ondalıklı giriş neden açık kalıyor?

Vendor input MinValue/MaxValue alanı display/keypad-domain değeridir. Statik derleyici yolu atof → binary64 → pow(10,F) → x87 çarpım → sıfıra doğru kesme yapıyor. Bu, raw29/F2'nin `0.29` sınırını bazı sayısal koşullarda28'e indirir. Exact decimal metin üretmek bu binary dönüşümü tek başına çözmez.

Bu nedenle **native numeric input F>0, `UNQUALIFIED_FIXED_DECIMAL` ile reddedilir**. Başlangıç PC53 kanıtı, sonradan thread rounding durumu/gerçek yüklenen CRT ve pow sonucunu kabul etmez. Sessiz nudge/epsilon veya limit değiştirme uygulanmaz. F0 mevcut raw input olarak kalır. [Araştırma](../reports/FIXED_DECIMAL_RESEARCH.md), [test/denetim](../reports/FIXED_DECIMAL_MILESTONE.json).

Gerçek Type6/F2 property örneği giriş ayarını doğrular; gerçek Type5/F>0 property holdout bulunmadı. Statik Type5 loader/formatter, generated Type5/F2 dosyası ve kavramsal browser ayrı kanıtlardır. Native piksel, keypad, compile, simulation, runtime ve panel kabulü NOT_RUN; tam V1 tamamlanmadı.

## Signed F0 ayrı kalır

[Static INT16/F0 dönüşümü](INT16_STORAGE.md) ayrı authority/descriptor ve explicit opcode gerektirir. Buradaki UINT F0..4 display veya common mathematical INT modeli, signed fractional native input/display ya da scaling kabulü açmaz.

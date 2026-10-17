# Mevcut WORD sayı alanları

Sayı ayarıyla birlikte ayrı izin isteği için [giriş izni sözleşmesi](EXISTING_ENTRY_PERMISSION.md) kullanılabilir. Numeric original-disabled guard değişmez; işlemler aynı original üzerinde doğrulanır. Numeric commit anında izin tekrar kontrolü iddiası taşımaz.

Bu yol yalnız kaynakla pinlenmiş B10 model2953863504 / serialized4.00.07.04 kapalı graph içindeki mevcut Type5/Sub1 gösterge ve Type6/Sub1 girişleri düzenler. Kaynağın signed INT veya unsigned UINT WORD temsili değiştirilmez. Kabul saklanmış ayar ve dosya bütünlüğü kapsamındadır; native piksel, vendor derleme, tuş takımı/runtime ve fiziksel kabul ayrı kalır.

```powershell
.venv/Scripts/python.exe scripts/qualify_existing_edit.py --workspace projects/ornek --source inputs/source.dps --output-dir calibration/R002 --source-reference "Kaynak kaydı" --review-reference "Bağımsız inceleme" --integer-numeric
```

Helper kaynak native dosyasını değiştirmez veya aday üretmez. Dört proje-local JSON verir; profil adı `existing_edit_numeric_v1` olur. Önceki `existing_edit_v1` değişmez. Ek descriptor, tam source SHA ve kayıtlı `dopsoft2_b10_integer_numeric.json` authority kitabına bağlıdır. `qualified=true`, keyfi yeniden hash veya başka kaynak profilinin kopyası bu yetkiyi açmaz. Kayıtlı kitap/profile/witness/source tekrar çağrılarda ve kayıt sonrasında yeniden kontrol edilir.

Kaynak nesnesi `native_integer_numeric` olarak belirtilir. `native_id`, tam `source_owner_sha256`, boş `text`, aynı kaynak bağları ve geometri korunur; `presentation: {}` yalnız sayı ayarı için yeterlidir. Ayrı görünüm isteği varsa aynı owner üzerinde original State pinleriyle birleşebilir. `integer_numeric` alanı `data_type`, `value_model: "integer_fixed_decimal"`, `integer_digits`, `fractional_digits` taşır. Input için ayrıca integer `raw_minimum` ve `raw_maximum` zorunludur.

| Kaynak türü | İzin verilen istek |
|---|---|
| INT WORD gösterge | F0, F1 veya F4; I=5−F |
| UINT WORD gösterge | F0–4; I=5−F |
| INT WORD giriş | Kaynak ve istek F0; −32768≤raw_minimum<raw_maximum≤32767 |
| UINT WORD giriş | Kaynak ve istek F0; 0≤raw_minimum<raw_maximum≤65535 |

I ve F açık integer'dır; gösterge tüm ham WORD aralığını kapsar. F4 signed gösterge ham−32768'i metinsel olarak−3.2768 şeklinde sunmayı amaçlar; PLC register değeri veya ölçeği değiştirilmez. Giriş basamak sayısı1–5 ve iki raw sınırı gösterecek kadar büyük olmalıdır. Sınırlar ham PLC integer değerleridir; engineering-unit dönüşümü yapılmaz. Native scalar limit kaynakta `0.000000` gibi eşdeğer integral yazılmışsa no-op bu yazımı byte eşit korur.

Yalnız `IntNum`, `DotNum` ve input `MinValue`/`MaxValue` değişebilir. `MemLen`, `MemFmt`, Gain1/Offset0/Roundoff0, read/write adresleri, driver, kanal/istasyon, birim, caption, States, macro ve kaynaklar korunur. Kaynak F>0 input, başka genişlik/format, identity dışı ölçek, aktif offset/visibility/interlock/trigger, dinamik sınır, custom keypad veya bilinmeyen alan açık hatadır. F>0 input endpointleri matematiksel olarak uygun görünse bile bu yol onları kabul etmez; vendor CRT/compiler/keypad dönüşümü doğrulanmış değildir.

Public IR otomatik `configure_existing_integer_numeric` opcode'una çevrilir. Explicit operation listesi exact intent ile eşleşmek zorundadır. Numeric ve presentation orijinal BODY kayıtlarında birleşir; inert silme ve opak arka planla aynı transaction içinde kaydedilebilir. No-op bütün native dosyada byte eşittir. Yeniden açılan dosya emitter'dan bağımsız IR/original kayıt haritasıyla karşılaştırılır; değişmemiş alanları ve ters yerine koymayla orijinal gövdeyi korumalıdır.

Önizleme kaynak kontrollerini **UNKNOWN · NATIVE NOT RENDERED** gösterir. Sayısal örnek veya browser fontuyla native görsel PASS üretilmez. İstenen PNG varsa arka plan tek başına gösterilir. İnsan onayı exact design/profile/source/operations hash'ine bağlıdır; başka basamak/sınır isteği eski onayla kaydedilmez. [Doğrulama](../reports/VERIFICATION.md) kabul edilmiş test revision'ını, [goals](GOALS.md) açık tam V1 işleri gösterir.

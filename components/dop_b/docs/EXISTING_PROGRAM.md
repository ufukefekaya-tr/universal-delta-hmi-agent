# Mevcut programda sabit yazı kaldırma

Bu yol, tam görsel düzeltme paketinin ilk dosya bileşenidir. **Paket hazır bildirimi değildir.** Mevcut programdaki açıkça seçilen inert `Type10/SubType6` nesnelerini tam Element+State byte aralıklarıyla kaldırır. Canlı nesne, adres, davranış, sayfa adı/sırası, geometri, kimlik, font, alarm/makro ayarı ve arka plan verisini değiştirmez.

Kapsam: gerçek kaynakla sabitlenmiş DOPSoft2/B10 `model_id=2953863504`, serialized editor `4.00.07.04`. Uzantı, klasör adı veya `qualified=true` bu desteği başka modele açmaz. DIAScreen, diğer B modelleri ve geniş program üretimi bu kapının dışında kalır.

## Proje içinde kullanım

Repo ve proje çalışma dizini ayrıdır. Aşağıdaki yollar örnektir; kaynak/girdiler proje çalışma dizinine göre relative olmalıdır. Host veya müşteri yolu çekirdeğe gömülmez.

```text
python scripts/calibrate_existing.py --workspace <PROJECT_WORKSPACE> --source inputs/source.dps --output-dir calibration/inert_v1 --source-reference "Kaynak kayıt kimliği" --review-reference "Kaynak inceleme kayıt kimliği"
```

Helper yalnız `existing_calibration.json` ve `profiles/existing_program_v1.json` üretir. Native aday oluşturmaz, mevcut dosya üzerine yazmaz. Ayrı stdio sunucusunu oluşturulan profile dizini ve proje workspace'iyle başlat:

```text
python -m universal_hmi.cli --profiles <PROJECT_WORKSPACE>/calibration/inert_v1/profiles serve --workspace <PROJECT_WORKSPACE>
```

Dokuz MCP aracı kullanılır. `open_project` kaynak, model, sürüm, kayıt biçimi ve registered static authority'yi doğrular. `inspect` envanterinden tüm sayfaları aynı sırada, tüm tutulacak nesneleri exact `native_preserved` IR ile temsil et. Her survivor'ın `native_id`, kaynak Element+State SHA'sı, boş IR metni ve kaynak geometrisi aynen bulunmalıdır. Yalnız silinmesi onaylanan inert yazıları tasarımdan çıkar. `plan_changes` için `operations=null` otomatik ve hash ile sabitlenmiş `delete_literal` işlemlerini oluşturur.

`preview` kavramsal IR gösterir; tutulmuş native nesneleri yeniden çizdiğini iddia etmez. Native görünüm veya eski yazının arka plan pikselinde kalmadığı kabulü bu önizlemeden çıkarılmaz. Sürüm ve hash'lerle bağlı insan onayı sonrası `validate → apply_plan → save_as → diff` kullanılır. Aynı çağrı ikinci nesne/sayfa üretmez. Ayrı kaydedilmiş aday yeniden çözümlenir; IR'den ayrı kurulan tam beklenen gövde ve çıkarılan aralıkları geri koyma kontrolü kaynak gövdeyi byte-exact geri getirir. No-op bütün dosyayı byte-exact korur.

## Kapatılan ve açık bırakılan sınırlar

- Yalnız grup, adres, görünürlük bağı, hareket/açı/dondurma ve picture/sound/blink davranışı bulunmayan tam inert literal kaldırılır. Canlı buton/numeric/indicator/goto çıkarma reddedilir. Survivor kimlikleri yeniden numaralanmaz.
- Başlık, global recipe/history/aux/macro ve resource shape kapıları bilinmeyen ilişkiyi varsayarak geçmez. Bilinmeyen, tekrarlı, eksik veya tutarsız kayıt açık hata verir.
- Native global macro-body kayıtları bu dar kaynak shape'inde desteklenmez; boş olduğu söylenen tanınmayan body de reddedilir. `SubMacroProtect/PWD001..512` yalnız ayrı, incelenmiş yapılandırma alanlarıdır. Password'un sekiz byte scalar sınırı gözlenen source subset'idir; üretici `%s` yazıcısının evrensel sabit genişliği değildir.
- AlarmCount korunmuş bounded scalar'dır; sıfır/nonzero'dan alarm kapasitesi/lifecycle sonucu çıkarılmaz. Kaynakta serialized alarm-entry/history kaydı bulunması bu subset'i kapatır.
- Existing background varsa her sayfa için tek ve tam, aynı canvas boyutlu BI_RGB32 DIB gerekir; offset/başlık/piksel/tail aynen korunur. Arka plan düzenleme ve PNG ekleme desteği değildir.
- Kaynak, witness, profil veya authority dosyası değişirse plan/apply/save durur. Helper sırasında kaynak veya authority kaybolması/okunamaz olması `CALIBRATION_CHANGED` verir; yarım native çıktıyı bırakmaz.

[Milestone](../reports/EXISTING_PROGRAM_MILESTONE.json) ve [bağımsız inceleme](../reports/EXISTING_PROGRAM_REVIEW.md) exact test/source/kanıt kapsamını taşır. Vendor derleme, native pixel, runtime ve panel kabulü `NOT_RUN` kalır. Önceki 623 testin WIP'yi kapsadığı iddia edilmez; escrow tarihsel ve değiştirilmeden korunur.

Mevcut görünüm/font/geometri düzenlemesi, PNG→DIB arka plan değişimi, signed F1/F4 giriş limitleri ve quality/interlock bütünleştirmesi hâlâ birlikte tamamlanacak işlerdir. Bunlar tamamlanmadan diğer proje ajanına toplu hazır bildirimi gönderilmez.

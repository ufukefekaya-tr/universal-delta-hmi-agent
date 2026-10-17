# Birleşik değişiklikte kaynak koordinatını koruma

Gözlem: ordinary scalar büyüdüğünde veya önceki owner silindiğinde aday BODY offset'leri kayar. Background frame offset'i o adayda yeniden yorumlamak yanlış sayfa çizimini bozabilir. SRAM içindeki metne benzeyen byte'lar resource header gibi aranırsa sahte frame bulunabilir.

Kök neden: değişikliklerin kendi yeni koordinatını tek immutable kaynağın adresiyle karıştırması; binary framing yerine metin marker'ıyla resource arama.

Karşı görüş: her alt değişiklik kendi parser'ından geçiyorsa sıra farkı önemsizdir. Somut karşı örnek; scalar bir byte büyürken background offset'i eski BODY'de kalır. Ayrı primitive PASS'i birleşik adayın whole-body eşitliğini kanıtlamaz.

Minimum değişiklik: bütün silme/scalar/frame span'ları orijinal kaynakta türetilir ve çakışma reddedilir. Binary payload yalnız kendi declared uzunluğuyla atlanır. Public IR'dan ikinci bağımsız raw expectation türetilir; gerçek saved/reopen/replay adayı tamamen karşılaştırılır. Görsel katmanı taklit etmeyen background-only önizleme ayrı tutulur.

Test: gerçek SDK dokuz-tool plan/apply/save/diff/replay; no-op byte eşitliği; independent original-record ve bottom-up BGRFF oracle; operation sırası permütasyonları; SRAM payload'ında tam sahte Background/DeviceTable header'ı; canlı owner retention; stale PNG/pin; new-only yayın sonrası PNG yarışı; malformed profile mode list/dict typed refusal. Bağımsız denetmenin E3 bulgusu erken mode-membership işleminin raw TypeError ürettiğini gösterdi; str guard ve public sıfır-session regresyonu eklendi. E4 karşı örneği; PNG’siz zero-image önizlemenin PNG gösterilmiş demesiydi. Missing/None bytes typed refusal, no-background truthful policy ve CLI render-before-publication ile kapandı. [751root/independent kabul](../reports/EXISTING_EDIT_MILESTONE.json) ve [denetim](../reports/EXISTING_EDIT_REVIEW.md) bütün test/review sayılarını bağlar.

Rollback: kaynak değişmez. Yeni output ayrı revision'dır; kayıt başarısızlığında yalnız kendi hash-eşit çıktısı temizlenir. Eski existing_program/native_preserved kapıları genişlemez; profile mevcut modu seçerek yeni özelliği kapatabilir. Runtime/vendor veya güncel dosyada görsel kabul varsayılmaz.

Genellenebilirlik sınırı: source-pinned B10 closed graph/version ve exact scalar/frame alt kümesi. Ortak örnek, vendor kabulü değildir. Özel makine görsel/tag/yolu repo içine taşınmaz. Bağımsız full-suite bounded existing_edit kabulü, tam numeric/quality/interlock batch kabulü değildir; fullbatch ve vendor/runtime açık kalır.

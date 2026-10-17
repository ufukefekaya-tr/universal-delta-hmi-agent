# Teknik karşı inceleme kayıtları

İlk entegrasyon denetmeni `/root/uhmi_native` kendi native modülünü kabul etmedi; root'un ayrı service/MCP katmanını çürütmeye çalıştı. İlk hüküm **FAIL**. İkinci denetmen `/root/uhmi_final_technical` hiçbir uygulama dosyası yazmadı. Tekrar testler final rapora bağlanır.

| Bulgu | Tetikleyici → kanıt → etki → düzeltme → tekrar test |
|---|---|
| H1/H2 | Yanlış model/editor veya native100×80–preview1024×600 → no-op plan geçebiliyordu → yanlış hedefe aday → gerçek envanter/model/editor/DocSize/PanelSize eşitliği → wrong_target/noop ve dimensions regresyonları. |
| H3 | Native clone preview'de yok → ek nesne görünmeden kaydedildi → inceleme kapsam dışı kalır → screen/element bijection ve unique native alias → extra/missing clone karşı testi. |
| H4 | Aynı adres, link/memory type değişikliği → basit string karşılaştırması geçti → yanlış kanal → exact binding contract/native metadata → same-address different-link karşı testi. |
| H5 | Native yazan buton IR feedback gösterge → önizleme yazmayı gizledi → komut fiziksel durum gibi göründü → kind/behavior ve write absence doğrulama → writable/readonly karşı testi. |
| M6/M7 | Onay geri çekme veya bozuk plan → save eski onayı kullanır/TypeError → geçersiz kayıt veya yapılandırılmamış hata → her save/repeat-save onay hash kontrolü ve schema → revoke/malformed regresyonları. |
| M8 | Native makro ilanı → validate geçer, apply reddeder → sahte PASS → validate ve apply aynı feature gate → native macro negatif testi. |
| H9 | State.Value ters → indeks durum kabul edildi →0/1 anlamı ters → native Value ile eşleme → actual_state_value testi. |
| T1 önemli | Desteklenmeyen font/layer/style/native numeric ve station/order → sessiz atlandı → görünüm/adres gerçek dosyayla farklı → strict IR alanları, native emission alan/binding guard, gerçek production gate kapalı → unknown/emission/controller testleri. |
| T2 önemli | REAL metre okuma, rpm yazma → sayısal giriş geçer → yanlış proses değerine yazma → aynı logical tag/type/unit ve bilinmeyen giriş görünümü → split binding ve unit testleri. |
| T3 önemli | Maintained0/1 aynı metin/renk → geçer → durum anlaşılmaz → distinct normalize caption/color → ambiguous bool testi. |
| T4 düşük | CSS#123 nativeRGB24=291 → renkler farklı → renderer/native uyuşmazlığı → native state fill yalnız6hex → shorthand/alpha negatif testleri. |
| D1 düşük | Destek tablosunda stale registryID → ajan yanlış profil seçer → doküman güncellemesi → registry ve check_repo kontrolü. |

Bu karşı testlerin kapanması yalnız framework/synthetic subset kabulünü sağlar. Gerçek numeric/macro/alarm/history/style emitter açıkken tamV1 ilan edilmez. Ajanların aynı fikirde olması test veya vendor kanıtı değildir.

## Son bağımsız karşı senaryolar ve kapanış

| Bulgu | Tetikleyici → kanıt → etki → düzeltme → tekrar test |
|---|---|
| F1 önemli | Element'ten sonra dolu/bilinmeyen AuxKey section → clone/delete yeni nesneye yanlış byte sınırı ekleyebilir → opaque kaynak mülkiyeti bozulur → kalibre edilmemiş structural extent/insertion reddi → property/no-op unknown retention ve üç structural negatif test. |
| F2 orta | 5000 digit ID/X/Value → Python int conversion ham ValueError → yapılandırılmamış hata → conversion öncesi canonical ID ve digit sınırı → INVALID_ID/NATIVE_LIMIT/NATIVE_INTEGER karşı testleri. |
| F3 önemli | İki Type/ReadVar/BgColor/wTextLen0 → fields dict son değeri seçer → conflicting native metadata onaylı preview gibi kabul edilir → yalnız controlled native alanların projection öncesi unique olması ve canonical language key → duplicate/alias negatif testler; opaque MemLen/MemFmt/Recipe grup tekrarları korunur. |
| P1 orta | Yeni design/preview/approval → Git ignore yalnız input/delivery/evidence → müşteri tagları yanlışlıkla genel repoya girebilir → bütün projects/*/ ağacı ignored, README izlenir → git check-ignore gerçek pattern regresyonu. |
| P2 önemli | POSIX venv/python symlink → resolve base interpreter'a gider → MCP paketi bulunmaz → interpreter invocation absolute korunur → gerçek linked-path JSON/TOML regression. |
| P3 düşük | macOS os.name=posix → Linux runtime yanlış PASS → kanıt OS kimliği yanlış → sys.platform Linux/macOS ayrı sonuç; çalışılmayan OS NOT_RUN → source review; Linux/macOS çalıştırma kabulü yok. |
| P4 orta | CRLF worktree → LF Git clone → ham kaynak/manifest SHA'ları farklı → metin LF normalizasyonu ve deterministic LF writer → source scan zeroCRLF, byte-only aesthetic rebind, temiz clone revision eşitliği kapısı. |

Fonksiyonel tekrar inceleme turuna estetik tur sınırı uygulanmadı. Bütün açık önemli implementation bulguları kapandı; FrameworkReady için clean-env/release kanıtı ayrıca gerekir.

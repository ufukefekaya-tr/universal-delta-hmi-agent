# Hesap değişimi için görev devri

**İnsan ara istedi; çalışma duraklatılacak. Görev tamamlanmadı.** Bu dosya yeni ajanın giriş noktasıdır. Bilgisayar kontrolü, vendor IDE/PLC/panel işlemleri yasaktır; PLC ajanının bilgisayar önceliği sürer. Çalışma yalnız genel repo ve dosya MCP'si üzerinden devam eder.

## Korunan durum

- Son denetlenmiş uygulama kaynağı: `567e25ef3849ab448d5f29d377adb17a9cb17a5e`. 67 kaynak SHA /623 benzersiz test; root ve bağımsız denetmen PASS,424 ek negatif senaryo. Revision `853bb797bfc1d1d9f18695e4c8aadde821554fb900bb2b9ef2d6dd6ae3f6bd63`.
- Son salt-okunur araştırma: `1bc4690d1c82d0ebc6e9b29284356e207f3ffe3a`; [görünüm/arka plan/silme kanıtı](../reports/PRESERVED_PROGRAM_RESEARCH.json), [uygulama kapıları](PRESERVED_PROGRAM_PLAN.md).
- [Tam makine okunur devir](../reports/ACCOUNT_HANDOFF.json) en son keypad/compiler/interlock bulgularını, artifact SHA'larını ve açık işleri taşır. Bunlar yeni capability kabulü değildir.
- Yarım kalan özgün kod WIP kaydında (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/wip/existing_program.py.txt`) byte-exact korundu. Runtime kaynak ağacından çıkarıldı; import/public MCP yolu yok. SHA `640bbd4dae3f8e4720f671e15b3afbef9c0dc5879e85726bd9ff64b36d6e043c`. Test dosyası yok, test ve SDK NOT_RUN. Gerçek kaynakta Recipe boş CRLF satırı nedeniyle ilk kontrol reddedildi; düzeltilmedi. Bunu hazır destek sayma.
- Eski clean RAR (tarihsel yerel kanıt; genel pakete dahil değil: `../dist/Universal_HMI_Agents_V1_CLEAN_20261013.rar`) b709/532-test snapshot'ıdır; güncel567e25e kaynağı ve bu devir/WIP onda yoktur.

## İlk devam adımı

İnsan açıkça devam dedikten sonra repo kökünü aç. `AGENTS.md`, `SYSTEM_PROMPT.md`, `INDEX.md`, `prompts/roles/programmer.md`, bu belge, `.agent-state/UHMI-V1-20261011/TASK_ENVELOPE.json` ve `SESSION_CHECKPOINT.json` tamamen okunur. Önceki sohbet özeti kaynak yerine geçmez.

```text
.venv/Scripts/python.exe tools/session_guard.py --task-id UHMI-V1-20261011 resume
```

Yeni host'ta ortam/yollar [taşıma rehberine](PORTABILITY.md) göre yeniden kurulur; eski `.venv`, account credential veya host config core'a gömülmez. Aynı PC'de repo ve ignored proje girdileri yerinde kalır. Git clone/clean RAR özel ignored kaynakları, calibration/property kanıtlarını ve `.agent-state` dosyalarını kendiliğinden taşımaz; yetkili çalışma girdileri ayrıca korunmalıdır.

WIP geri alınmadan exact writer scope/lease yeniden verilmelidir. Önce `ExistingProgram` guard/framing sorunları, anlamlı neutral testler ve bağımsız gerçek-body/source-restoration incelemesi tamamlanır; ardından profile/helper/service/9SDK bütünleştirilir. Eski623 PASS sonucu yarım kodu kapsamaz.

## Açık paket

Mevcut nesne geometri/font/style, inert yazı silme, opak PNG→mevcut aynı boyutlu DIB, signedF1/F4 giriş sınırları ve quality/interlock birlikte tamamlanıp denetlenecek. Kullanıcı diğer proje ajanına alt özelliklerle sayfaları tamamlatmak istemiyor; tek denetimli paket hazır olduğunda topluca uygulanacak. Özel proje varlıkları/tagları/sabit yollar genel çekirdeğe taşınmayacak; o projenin dosyalarına bu ajan yazmayacak.

Önemli teknik sınırlar: nativeStyle3 text-only'dir; runtime16 dosyaya yazılmaz. Button/indicator yüzeyi FgColor, numeric flat BgColor kullanır. FontRatio0/48→100 eşdeğer normalizasyon değildir. Background ham PNG değildir; iç DIB/offset graph ayrıca doğrulanır. Runtime keypad decimal→integer yolu statik doğrulandı, fakat compiler'ın atof/pow/x87 limit indirgemesi açık. Interlock tekBOOL'dur; TriggerVar farklı yazma işlevi, VisibleVar okuma hatasında eski görünürlüğü korur; OR/stale mask/post-keypad kilit garanti edilmedi.

G2/G3 tam feature integration, gerçek DIAScreen kaynak/driver/macro/alarm/history ve iki native pilot; G5/G7 vendor/panel insan kabulü açık. FrameworkReady veya dosya üretimi tam V1 kabulü değildir.

## Kayıt ve güvenilir devam

Checkpoint, `1bc4690` araştırma commit'inde commit kapısının staging'den önce çağrılıp başarısız sonuçtan sonra işlemin sürmesini açıkça kaydeder. Kapsam/index/parent/kaynak bütünlüğü doğru kaldı, fakat geçmiş kapı PASS diye yeniden adlandırılmaz. Doğru sıra: edit gate PASS → exact staging → commit gate PASS → commit → parent/path/hash kontrolü → root-only checkpoint. Her başarısız kapıda bağlı işlem durur.

Hesap değişiminde eski sohbetlere erişim kalmayabilir; bu yerel devir ve hash'ler korunmuş kaynaktır. Başka ajana mesaj yetkisi ve erişimi yerel kayda/güncel insan talimatına göre doğrulanır. Kısmi destek için hazır bildirimi gönderilmez. Duraklama tamamlanma değildir.

# Rol kartları

**0.2.0 headless yolu:** [Tek görev başlangıç yetkisi, workflow/goals ve teslim sınırı](../../docs/HEADLESS_RELEASE.md). Etkileşimli insan onayı kuralları legacy akışta korunur; headless işte güvenilen başlatıcı policy’si ve exact bağımsız teknik/sıralı estetik incelemeler uygulanır. İş girdisi kendine yetki veremez. Önceki V1/two-family/vendor/panel goals açık kalır.


Roller kanonik politikayı kopyalamaz; görev farkını tanımlar. Orkestratör envelope'de exact scope ve owner atar. Reviewer read-only'dir; aynı dosya, tag kataloğu, global state veya fiziksel çıkış paralel yazarlara verilmez. Checkpoint ve ortak commit tek orkestratör tarafından yönetilir.

| Rol | Çıktı |
|---|---|
| [ANALYST](ANALYST.md) | Kanıtlı hedef/girdi/işlev contract ve eksikler |
| [ARCHITECT](ARCHITECT.md) | Adapter/profile/blok sınırları ve acceptance planı |
| [DESIGNER](DESIGNER.md) | Tasarım, binding/behavior contract ve sürümlü preview |
| [PROGRAMMER](PROGRAMMER.md) | Qualified planın scope içi uygulaması, yeni çıktı |
| [VERIFIER](VERIFIER.md) | Bağımsız offline test ve meaningful diff |
| [TENTH_MAN](TENTH_MAN.md) | Read-only teknik karşı inceleme ve failure chain |
| [AESTHETIC_FIRST](AESTHETIC_FIRST.md) | İlk bağımsız operatör/görsel inceleme |
| [AESTHETIC_SECOND](AESTHETIC_SECOND.md) | Sıralı ikinci inceleme; ilk rapor ve uygulayıcı eleştirisi |
| [KAIZEN](KAIZEN.md) | Neutral sınırlı ders ve regresyon önerisi |

Her rol başlangıçta control plane/assigned envelope/checkpoint ve görevle ilgili kaynakları okur; resume gate geçirir. Gate metadata doğrulamasıdır, okuma/anlama ispatı değildir. Üretim tasarımındaki teknik review, sıralı iki estetik review ve insan versioned preview approval atlanmaz.

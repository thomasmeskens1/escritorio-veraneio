"""Biblioteca de músicas das marcas, gerada por IA local (ACE-Step 1.5, licença MIT, uso comercial liberado) para o
Thomas aprovar (Sonoplasta, passo 3; 05/11/2026). Roda com o Python do ACE-Step, em prioridade baixa (o PC segue
usável), ~4,5 min por 30 s de música no processador.

Direção aprovada: Casa Veraneio parte da bossa (aprovada) e explora outros ritmos de praia; Corporativo só
eletrônico, com energia; NUNCA piano + cordas cinematográfico (a amostra "de velório" do Corp). Casa Vero: a definir.

Cada faixa sai em MP3 na pasta de aprovação e entra em `catalogo.json` (marca, estilo, BPM, clima, arquivo,
status), que o Sonoplasta vai ler para escolher a trilha de cada vídeo.

Uso (no C:\\dev\\ace-step):  uv run python <este arquivo> <pasta de saída> [marca ...]
"""

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

DURACAO = 40  # segundos: cobre Reels e stories; o Sonoplasta corta, repete ou estende no vídeo

FAIXAS = {
    "CASA VERANEIO": [
        ("bossa_nova_praia", 100, "tarde de praia, luxo, relaxado",
         "instrumental bossa nova, nylon acoustic guitar, brushed drums, upright bass, soft flute melody, warm, "
         "sunny beach afternoon, luxury villa, relaxed, 100 bpm"),
        ("tropical_house", 110, "pôr do sol, leve, alegre",
         "instrumental tropical house, marimba and steel drum melody, plucked synths, soft four on the floor kick, "
         "warm bass, sunny beach sunset, uplifting, 110 bpm, no vocals"),
        ("balearic_chill", 95, "golden hour, brisa do mar",
         "instrumental balearic chillout, acoustic guitar arpeggios, warm analog pads, slow groove, ocean breeze, "
         "golden hour at the beach, dreamy, 95 bpm"),
        ("samba_jazz_leve", 120, "verão, festa leve, brasileiro",
         "instrumental light samba jazz, brazilian percussion, pandeiro, acoustic guitar, rhodes electric piano, "
         "joyful summer, sunny, 120 bpm"),
        ("deep_house_organico", 118, "beach club, sofisticado",
         "instrumental organic deep house, brazilian percussion, kalimba, warm deep bass, smooth groove, luxury "
         "beach club, relaxed, 118 bpm"),
        ("lounge_nu_jazz", 105, "fim de tarde, drinque no bar da piscina",
         "instrumental nu jazz lounge, muted trumpet, vibraphone, smooth bass, light drums, cocktail by the pool, "
         "elegant, 105 bpm"),
    ],
    "CASA VERANEIO CORP": [
        ("progressive_house", 126, "celebração, energia de festival",
         "instrumental uplifting progressive house, bright synth leads, driving kick, sidechained pads, festival "
         "energy, celebration, 126 bpm"),
        ("nu_disco", 120, "festa, dançante, sorriso",
         "instrumental nu disco, funky slap bassline, electric guitar chops, groovy drums, synth stabs, party, "
         "joyful, 120 bpm"),
        ("tech_house", 125, "evento moderno, pulsante",
         "instrumental tech house, punchy kick, rolling bassline, percussive hi hats, modern event, energetic, "
         "125 bpm"),
        ("melodic_techno", 122, "noite, elegante, imersivo",
         "instrumental melodic techno, arpeggiated synths, deep pulsing bass, wide atmosphere, elegant night "
         "event, driving, 122 bpm"),
        ("electro_pop", 118, "lançamento, otimista",
         "instrumental electro pop, catchy synth hook, upbeat drums, bright and optimistic, product launch, "
         "118 bpm, no vocals"),
        ("future_house", 124, "virada, energia alta",
         "instrumental future house, bouncy metallic bass, bright plucks, energetic build and drop, 124 bpm"),
    ],
}


def _prioridade_baixa() -> None:
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # abaixo do normal


def gerar(pasta: Path, marcas: list[str]) -> None:
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    _prioridade_baixa()
    dit = AceStepHandler()
    dit.initialize_service(project_root=str(Path.cwd()), config_path="acestep-v15-turbo", device="cpu")
    catalogo_arquivo = pasta / "catalogo.json"
    catalogo = json.loads(catalogo_arquivo.read_text(encoding="utf-8")) if catalogo_arquivo.exists() else []
    feitos = {item["arquivo"] for item in catalogo}
    for marca in marcas:
        destino = pasta / marca
        destino.mkdir(parents=True, exist_ok=True)
        for estilo, bpm, clima, legenda in FAIXAS[marca]:
            arquivo = f"{marca}/{marca.title().replace(' ', '_')}_{estilo}.mp3"
            if arquivo in feitos:
                continue
            t0 = time.perf_counter()
            params = GenerationParams(task_type="text2music", caption=legenda, lyrics="[Instrumental]",
                                      duration=DURACAO, inference_steps=8, shift=3.0, thinking=False)
            r = generate_music(dit, LLMHandler(), params, GenerationConfig(batch_size=1, audio_format="wav"),
                               save_dir=str(Path.cwd() / "biblioteca_wav"))
            if not r.success:
                print(f"ERRO {arquivo}: {r.error}", flush=True)
                continue
            wav = Path(r.audios[0]["path"])
            wav = wav.rename(wav.with_name(Path(arquivo).stem + ".wav"))  # o original fica no PC, fora do Drive
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "320k",
                            str(pasta / arquivo)], check=True)
            catalogo.append({"marca": marca, "estilo": estilo, "bpm": bpm, "clima": clima, "duracao": DURACAO,
                             "arquivo": arquivo, "original": str(wav), "legenda": legenda,
                             "modelo": "ACE-Step 1.5 turbo (MIT)", "status": "para aprovação"})
            catalogo_arquivo.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"OK {arquivo} em {time.perf_counter() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    gerar(Path(sys.argv[1]), sys.argv[2:] or list(FAIXAS))

#!/usr/bin/env bash
# Confere se todos os arquivos entregues nessa sessão estão presentes
# e com o conteúdo certo no seu sistema — roda a partir de ~/carbonara-py

set -u
cd ~/carbonara-py || { echo "Não achei ~/carbonara-py"; exit 1; }

declare -A ESPERADOS=(
  ["/usr/local/bin/carbonara-helper"]="2a20dd0d3ee511667205dea037fdf1f83f0ed905fa640fcebc325ac9c24b5562"
  ["core/snapshots/restore.py"]="6d3909d93d45fbaf707a4b30f98791ce595f9a1296de1a07363976156ecb8408"
  ["core/snapshots/backup.py"]="10aef81641fb24b6dc9071f4dc63da50804395e00f5d3c3a78a692fbfee9b112"
  ["core/eggs/eggs.py"]="9b6b570d2352893222c811365572a53f958710cb3549d550b5bd133b97a0845a"
  ["core/system/live_mount.py"]="832755cb7a97ccc84f09aa5ffe498b5c154e2514ac7268f94f24d7e18bf26ad4"
  ["ui/pages/eggs/eggs_page.py"]="f642d05681f0554d5ed2cad5818c5738857802a03842a450290871fb29043713"
  ["ui/widgets/eggs_progress.py"]="1de37f1c1a7cca79859dd1b2a40bfe2fedef8b51bda3114de054463446ca1260"
  ["ui/pages/backups/snapshots_page.py"]="05de62cb020f775ab08aeab1cd0e7d8379e33f350fb02865fc638de29ca4eb63"
  ["ui/widgets/backup_progress.py"]="34117f780752a452a6cbf83997b2d51fe73c0f72c786bd72f3714ec19e6a2f6f"
  ["ui/pages/disks/disks_page.py"]="348422c13db4f555f95b1616fb14fb94f50e396b49e3b87acba967e5a70f7277"
  ["ui/main_window.py"]="bcc7f20c909f292dc3b022da9a2d0882da632505278f6ff14d8269728c69238f"
  ["ui/pages/doctor/doctor_arch_page.py"]="30f8f0ce9a9279c0032414512ea96f0e5445be111fb2a9c9ae3528e5d4d524cf"
)

OK=0
FALHOU=0

for path in "${!ESPERADOS[@]}"; do
  esperado="${ESPERADOS[$path]}"
  if [ ! -f "$path" ]; then
    echo "❌ AUSENTE: $path"
    FALHOU=$((FALHOU+1))
    continue
  fi
  real=$(sha256sum "$path" | awk '{print $1}')
  if [ "$real" = "$esperado" ]; then
    echo "✅ OK: $path"
    OK=$((OK+1))
  else
    echo "❌ DIVERGENTE: $path"
    echo "     esperado: $esperado"
    echo "     atual:    $real"
    FALHOU=$((FALHOU+1))
  fi
done

echo ""
echo "==================================="
echo "OK: $OK   FALHOU: $FALHOU"
echo "==================================="

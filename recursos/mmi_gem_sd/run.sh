#!/bin/ksh

# 20241216 drger; Enable MMI3G Green Engineering Menu (GEM) v1

### Common functions ###
xgetgemstatus(){
 sqlite3 $1 "SELECT pst_value
  FROM tb_intvalues
  WHERE pst_namespace=4 AND pst_key=4100"
}
xenablegem(){
 sqlite3 $1 "UPDATE tb_intvalues
  SET pst_value=1
  WHERE pst_namespace=4 AND pst_key=4100"
}

### Script startup ###
xversion="v241216"
showScreen ${SDLIB}/gemenable-0.png
touch ${SDPATH}/.started
xlogfile=${SDPATH}/gemenable-$(getTime).log
exec > ${xlogfile} 2>&1
umask 022
echo "[INFO] Start: $(date); Timestamp: $(getTime)"

### 20241216 drger; Enable MMI3G Green Engineering Menu (GEM) script ###
echo "[INFO] Enable MMI3G Green Engineering Menu: gemenable-$xversion"

### Get Train and MainUnit software version ###
case "$MUVER" in
MMI3GB | MMI3GH)
  SWTRAIN="$(sloginfo -m 10000 -s 5 |
    sed -n 's/^.* +++ Train //p' | sed -n 1p)" ;;
esac # MUVER-SWTRAIN
echo; echo "[INFO] MU train name: $SWTRAIN"
MUSWVER="$(sed -n 's/^version = //p' /etc/version/MainUnit-version.txt)"
echo "[INFO] MU software version: $MUSWVER"

### Script magic here ###
for xdn in efs-persist hmisql
do
  xdb="/mnt/${xdn}/DataPST.db"
  xgemstatus="$(xgetgemstatus ${xdb})"
  if [ "$xgemstatus" = 0 ]
  then
    echo; echo "[ACTI] Enabling Green Engineering Menu (GEM) in ${xdb} ..."
    xenablegem ${xdb}
  elif [ "$xgemstatus" = 1 ]
  then
    echo; echo "[INFO] Green Engineering Menu (GEM) enabled in ${xdb} !"
  else
    echo; echo "[ERROR] No Green Engineering Menu record found in ${xdb} !"
  fi
done

### Script cleanup ###
echo; echo "[INFO] End: $(date); Timestamp: $(getTime)"
showScreen ${SDLIB}/gemenable-1.png
rm -f ${SDPATH}/.started
exit 0

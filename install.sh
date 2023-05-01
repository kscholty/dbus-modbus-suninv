#!/bin/sh

SOURCE=$0
while [ -L "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
  SOURCE=$(readlink "$SOURCE")
  [[ $SOURCE != /* ]] && SOURCE=$DIR/$SOURCE # if $SOURCE was a relative symlink, we need to resolve it relative to the path where the symlink file was located
done
PATH=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
DIR=`/usr/bin/basename $PATH`

if  [ ! -L /opt/victronenergy/$DIR ] 
then
  /bin/ln -s $PATH to /opt/victronenergy/$DIR
else 
  echo Service exists already
fi

if  [ -L /opt/victronenergy/service-templates/$DIR ] 
then
    /bin/rm /opt/victronenergy/service-templates/$DIR
fi

if  [ ! -e /opt/victronenergy/service-templates/$DIR ] 
then
  /bin/mkdir /opt/victronenergy/service-templates/$DIR
  /bin/cp -r $PATH/service/* /opt/victronenergy/service-templates/$DIR/
else 
  echo Service-template exists already
fi

if [ ! -e /data/conf/serial-starter.d ]
then
/bin/mkdir /data/conf/serial-starter.d
fi


if [ ! -e /data/conf/serial-starter.d/suninv.conf ]
then
/bin/cp $PATH/conf/serial-starter.d/suninv.conf /data/conf/serial-starter.d/suninv.conf
else 
echo serial-starter conf file already exists
fi


if [ ! "$1" == "NORC" ]
then
  echo Looking for rc.local
  if [ ! -e /data/rc.local ]
  then
    echo No rc.local found
    echo '#!/bin/sh' > /data/rc.local    
    /bin/chmod u+x /data/rc.local
  fi  
  echo $PATH/install.sh NORC >> /data/rc.local
else
  echo skipping rc.local test  
fi

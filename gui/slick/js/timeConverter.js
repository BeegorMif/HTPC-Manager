function pad(n) {
    return (n < 10) ? ("0" + n) : n;
}

function timeConverter(UNIX_timestamp){
 var a = new Date(UNIX_timestamp*1000);
 var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
     var year = a.getFullYear();
     var monthIndex = a.getMonth();
	 console.log("a.getmonth " + a.getMonth())
     var month = pad(monthIndex + 1);
     var date = a.getDate();
     var hour = a.getHours();
     var min = a.getMinutes();
     var sec = a.getSeconds();
     var time = year+'-'+month+'-'+date+'-'+hour+'-'+min ;
     return time;
 }
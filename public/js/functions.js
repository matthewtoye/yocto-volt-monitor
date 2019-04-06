var update_needed = false, 
	updateForever = setInterval("update_server()",1000),
	first_run = false;
	
function SelectSensor(){
	var dropdown = document.getElementById('sensorlist');
	var idx = dropdown.selectedIndex;
	var sens = dropdown.options[idx].value;
	if (document.getElementById("plot_img")) {
		document.getElementById("plot_img").src = "/static/images/plot." + sens + ".png?rand="+Math.random();
		document.getElementById("plot_img").value = sens;
	}
	if (document.getElementById("plot_img_mini")) {
		document.getElementById("plot_img_mini").src = "/static/images/miniplot." + sens + ".png?rand="+Math.random();
		document.getElementById("plot_img_mini").value = sens;
	}
	
	document.getElementById("sensor_label").value = sens;
	document.getElementById("sensor_label").innerHTML = sens;
	
	// disable updates temporarily while we update the page with information pertaining to selected sensor
	clearInterval(updateForever);
	first_refresh();
	updateForever = setInterval("update_server()",2000);
	
}

function RefreshSensorList() {
	$.ajax({
		type: "POST",
		url: "sensor_list",
		data: JSON.stringify({}),
		contentType: 'application/json',
		dataType: 'json',
		error: function() {
			alert("error");
		},
		success: function(data) {
			var select = document.getElementById("sensorlist");
			for (var i = 0; i < data.length; i++) {
				var opt = data[i];
				var el = document.createElement("option");
				el.textContent = opt['name'];
				el.value = opt['id'];
				select.appendChild(el);
				console.log("completed refreshsensorlist")
				
				if (!first_run) {
					first_run = true;
					SelectSensor();
				}
			}
		}
	});
}

function update_server() {
	var my_data;
	
	if (update_needed) {
		my_data = JSON.stringify({
			"sens": document.getElementById("sensor_label").value,
			"email": document.getElementById("dest_email").value,
			"target_value": document.getElementById("target_value").value,
			"method_to_use": document.getElementById("method_to_use").value,
			"type_of_check": document.getElementById("type_of_check").value,
			"enabled": document.getElementById("enabled").value,
			"stop_when_target_reached": document.getElementById("stop_when_target_reached").value,
			"recording": document.getElementById("recording").value,	
			"ip_in_control": document.getElementById("ip_in_control").innerHTML	
		})
		update_needed = false;
	} else {
		if (document.getElementById("plot_img_mini")){
			my_data = JSON.stringify({
				"sens": document.getElementById("sensor_label").value				
			})
		}
		
		else {
			my_data = JSON.stringify({
				"sens": document.getElementById("sensor_label").value,
				"email": document.getElementById("dest_email").value,
				"target_value": document.getElementById("target_value").value
			})
		}
	}
	$.ajax({
		type: "POST",
		url: "status",
		data: my_data,
		contentType: 'application/json',
		dataType: 'json',
		success: function(data) {
			
			// Mini page
			if (document.getElementById("plot_img_mini")) {
				document.getElementById("plot_img_mini").src = "/static/images/miniplot." + document.getElementById("sensor_label").value + ".png?rand="+Math.random();
				document.getElementById("current_voltage").innerHTML = data['voltage'] +"V ";
			}
			
			// Regular page
			else {
				document.getElementById("plot_img").src = "/static/images/plot." + document.getElementById("sensor_label").value + ".png?rand="+Math.random();
				document.getElementById("current_voltage").innerHTML = data['voltage'] +"V ";
				document.getElementById("stopwatch").innerHTML = data['stopwatch'] + " Seconds";
				document.getElementById("current_module").innerHTML = "Recording Module: " + data["current_module"];
				document.getElementById("module_recording_status").innerHTML = data["module_recording_status"];
				document.getElementById("ip_in_control").innerHTML = data['ip_in_control'];
				document.getElementById("dest_email").value = data["email"];
				
				// If we are not in control, update page with data so we know if it changes
				if (document.getElementById("ip_in_control").innerHTML != document.getElementById("your_ip").innerHTML) {
					document.getElementById("target_value").value = data["target_value"];					
					type_dropdown_changed(data);
					method_dropdown_changed(data);
					toggle_enabled(data);
					toggle_recording(data);
					toggle_stop_when_target_reached(data);	
				}
				// only update the recording button if we are transitioning from stop to start or start to stop
				if (document.getElementById("recording").innerHTML = "Please Wait..") {
					toggle_recording(data);
				}
				
				take_control(data);
			}
		},
		error: function(xhr) {
			parser = new DOMParser();
			xmlDoc = parser.parseFromString(xhr.responseText,"text/xml");
			console.log(xmlDoc.getElementById("traceback").innerHTML);
			clearInterval(updateForever);
			console.log("STOPPED AUTOMATIC UPDATES")
		}
	});
}

function type_dropdown_changed(js_obj) {
	// Used only for refresh
	if (js_obj) {
		document.getElementById("type_of_check").value = js_obj["type_of_check"];
	} 
	
	document.getElementById("method_to_use").innerHTML = "";
	dropdown = document.getElementById("method_to_use");
	
	switch (document.getElementById("type_of_check").value) {
		case "voltage":
			list = ["higher than", "lower than", "highest value for"];
			
			for (z = 0; z < list.length; z++) {
				el = document.createElement("option");
				el.textContent = list[z];
				el.value = list[z];
				dropdown.appendChild(el);
			}			
		 
		break;
		case "time":
			el = document.createElement("option");
			el.textContent = "elapsed for";
			el.value = "elapsed for";
			dropdown.appendChild(el);
		break;
		case "test":
			el = document.createElement("option");
			el.textContent = "test";
			el.value = "test";
			dropdown.appendChild(el);
		break;
	}
	
	if (!js_obj) {
		method_dropdown_changed();
		update_needed = true;
	}
}

function method_dropdown_changed(js_obj) {
	// Used only for refresh
	if (js_obj) {
		document.getElementById("method_to_use").value = js_obj["method_to_use"];
	} 
	
	switch (document.getElementById("method_to_use").value) {
		case "higher than":
		case "lower than":
		default:
			document.getElementById("type_of_check_text").innerHTML = "Volts";
		break;
		case "highest value for":
		case "elapsed for":
		case "test":
			document.getElementById("type_of_check_text").innerHTML = "Minutes";
		break;
	}
	
	if (!js_obj) {
		update_needed = true;
	}
}

function toggle_stop_when_target_reached(js_obj) {
	// Used only for the refresh
	if (js_obj) {
		// Update stop when target reached button to reflect current server value
		document.getElementById("stop_when_target_reached").checked = js_obj["stop_when_target_reached"];
		
		// Enabled - Update status
		if (js_obj["stop_when_target_reached"]) {	
			document.getElementById("stop_when_target_reached").value = "True";		
		} 
		
		// Disabled
		else {
			document.getElementById("stop_when_target_reached").value = "False";
		}
	}
	
	// Used when button changes state
	else {
		// Enabled
		if (document.getElementById("stop_when_target_reached").checked) {	
			document.getElementById("stop_when_target_reached").value = "True";	
		} 
		
		// Disabled
		else {
			document.getElementById("stop_when_target_reached").value = "False";
		}
		update_needed = true;
	}
}

function toggle_enabled(js_obj) {
	// Used only for the refresh
	if (js_obj) {
		// Update enabled button to reflect current server value
		document.getElementById("enabled").checked = js_obj["enabled"];

		// Enabled - Update enabled status
		if (js_obj["enabled"]) {	
			document.getElementById("enabled").value = "True";		
		} 
		
		// Disabled
		else {
			document.getElementById("enabled").value = "False";
		}
	}
	
	// Used when enable button changes state
	else {
		// Enabled
		if (document.getElementById("enabled").checked) {	
			document.getElementById("enabled").value = "True";	
			document.getElementById("recording").style.visibility = "visible";
		} 
		
		// Disabled
		else {
			document.getElementById("enabled").value = "False";
			document.getElementById("recording").style.visibility = "hidden";
		}
		update_needed = true;
	}
}

function take_control(js_obj) {
	// Used only for the refresh
	if (js_obj) {

		if (js_obj["your_ip"] && js_obj["ip_in_control"]) {	
			
			// We are in control - hide the take control button
			if (js_obj["your_ip"] == js_obj["ip_in_control"]) {
				document.getElementById("take_control").style.visibility = "hidden";	
			}
			
			// We are not in control
			else {
				document.getElementById("take_control").style.visibility = "visible";
			}
		} 
	}
	
	// Used when enable button changes state
	else {
		// We take control
		if (document.getElementById("take_control").style.visibility = "visible") {	
			document.getElementById("take_control").style.visibility = "hidden";	
			document.getElementById("ip_in_control").innerHTML = document.getElementById("your_ip").innerHTML;
		} 
		update_needed = true;
	}
}

function toggle_recording(js_obj) {
	// Used only for the refresh
	if (js_obj) {
		// visible - Update recording button visibility based on enabled button
		if (document.getElementById("enabled").value == "True") {
			document.getElementById("recording").style.visibility = "visible";
		}
		
		// hidden
		else {
			document.getElementById("recording").style.visibility = "hidden";
		}
		
		// Turn on recording - Update recording button text based on current recording status
		if (js_obj["recording"]) {	
			document.getElementById("recording").innerHTML = "Stop Recording";
			document.getElementById("recording").value = "True";		
		} 
		
		// Turn off recording
		else {
			document.getElementById("recording").innerHTML = "Start Recording";
			document.getElementById("recording").value = "False";		
		}
	}
	
	// Used when recording button is pressed
	else {
		document.getElementById("recording").innerHTML = "Please Wait..";
		
		// Turn on recording
		if (document.getElementById("recording").value == "False") {	
			document.getElementById("recording").value = "True";
				
			if (document.getElementById("method_to_use").value == "test") {
				document.getElementById("current_module").style.visibility = "visible";
				document.getElementById("module_recording_status").style.visibility = "visible";
				document.getElementById("stopwatch").style.visibility = "visible";
			}
		} 
		
		// Turn off recording
		else {
			document.getElementById("recording").value = "False";
			
			if (document.getElementById("method_to_use").value == "test") {
				document.getElementById("current_module").style.visibility = "hidden";
				document.getElementById("module_recording_status").style.visibility = "hidden";
				document.getElementById("stopwatch").style.visibility = "hidden";
			}
		}
		update_needed = true;
	}
}

function first_refresh() {
	$.ajax({
		type: "POST",
		url: "status",
		data: JSON.stringify({
			"sens": document.getElementById("sensor_label").value
		}),
		contentType: 'application/json',
		dataType: 'json',
		error: function(xhr) {
			parser = new DOMParser();
			xmlDoc = parser.parseFromString(xhr.responseText,"text/xml");
			alert(xmlDoc.getElementById("traceback").innerHTML);
		},
		success: function(data) {
			// Mini page
			if (document.getElementById("plot_img_mini")) {
				document.getElementById("current_voltage").innerHTML = data['voltage'] +"V ";
			}
			
			// Main page
			else {
				// Update email and voltage field
				document.getElementById("dest_email").value = data['email'];
				document.getElementById("current_voltage").innerHTML = data['voltage'] +"V ";		
				document.getElementById("target_value").value = data["target_value"];
				document.getElementById("current_module").innerHTML = "Recording Module: " + data["current_module"];
				document.getElementById("module_recording_status").innerHTML = data["module_recording_status"];
				document.getElementById("stopwatch").innerHTML = data['stopwatch'] + " Seconds";
				document.getElementById("your_ip").innerHTML = data['your_ip'];
				document.getElementById("ip_in_control").innerHTML = data['ip_in_control'];
				type_dropdown_changed(data);
				method_dropdown_changed(data);
				toggle_enabled(data);
				toggle_recording(data);
				toggle_stop_when_target_reached(data);	
				take_control(data);
			}
		}
	});
}
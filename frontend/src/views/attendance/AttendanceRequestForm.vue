<template>
	<ion-page>
		<ion-content :fullscreen="true">
			<FormView
				v-if="formFields.data"
				doctype="Attendance Request"
				v-model="attendanceRequest"
				:isSubmittable="true"
				:fields="formFields.data"
				:id="props.id"
				@validateForm="validateForm"
			/>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { createResource } from "frappe-ui"
import { ref, watch, inject } from "vue"

import FormView from "@/components/FormView.vue"

const employee = inject("$employee")
const __ = inject("$translate")

const props = defineProps({
	id: {
		type: String,
		required: false,
	},
})

// reactive object to store form data
const attendanceRequest = ref({})

// get form fields
const formFields = createResource({
	url: "hrms.api.get_doctype_fields",
	params: { doctype: "Attendance Request" },
	auto: true,
	transform(data) {
		const fields = props.id
			? data
			: data.filter(
					(field) => !["employee", "employee_name", "status", "company"].includes(field.fieldname)
			  )
		// Miyano: ngày nửa buổi luôn là ngày của đơn (đơn nửa ngày chỉ được trong MỘT ngày) nên không
		// hỏi lại; chỉ hỏi buổi Sáng / Chiều. FormView không đọc `depends_on`, nên tự bật/tắt ở dưới.
		return fields.map((field) => {
			if (field.fieldname === "half_day_date") field.hidden = true
			if (field.fieldname === "half_day") field.hidden = true
			if (field.fieldname === "custom_half_day_session") field.hidden = true
			return field
		})
	},
})

// form scripts
watch(
	() => attendanceRequest.value.employee,
	(employee_id) => {
		if (props.id && employee_id !== employee.data.name) {
			// if employee is not the current user, set form as read only
			setFormReadOnly()
		}
	}
)

watch(
	() => attendanceRequest.value.from_date,
	(from_date) => {
		if (!attendanceRequest.value.to_date) {
			attendanceRequest.value.to_date = from_date
		}
	}
)

watch(
	() => [attendanceRequest.value.from_date, attendanceRequest.value.to_date],
	([from_date, to_date]) => {
		validateDates(from_date, to_date)
	}
)

watch(
	() => [
		attendanceRequest.value.from_date,
		attendanceRequest.value.to_date,
		attendanceRequest.value.half_day,
		formFields.data,
	],
	([from_date, to_date, half_day, fields]) => {
		if (!fields) return
		const one_day = Boolean(from_date) && from_date === to_date
		const field = (name) => fields.find((f) => f.fieldname === name)

		// nửa ngày chỉ có nghĩa với đơn một ngày: nhiều ngày thì ẩn và bỏ tick
		if (field("half_day")) field("half_day").hidden = !one_day
		if (!one_day && half_day) attendanceRequest.value.half_day = 0

		const is_half = one_day && Boolean(half_day)
		attendanceRequest.value.half_day_date = is_half ? from_date : null

		const session = field("custom_half_day_session")
		if (session) {
			session.hidden = !is_half
			session.reqd = is_half
			if (is_half && !attendanceRequest.value.custom_half_day_session) {
				attendanceRequest.value.custom_half_day_session = "Sáng"
			}
		}
	}
)

// helper functions
function setFormReadOnly() {
	formFields.data.map((field) => (field.read_only = true))
}

function validateDates(from_date, to_date) {
	if (!(from_date && to_date)) return

	const error_message = from_date > to_date ? __("To Date cannot be before From Date") : ""

	const from_date_field = formFields.data.find((field) => field.fieldname === "from_date")
	from_date_field.error_message = error_message
}

function validateForm() {
	attendanceRequest.value.employee = employee.data.name
}
</script>

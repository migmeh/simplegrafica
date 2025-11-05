import { Component, OnInit } from '@angular/core';
import { ChartModule } from 'primeng/chart'; // ⬅️ Importa el módulo


@Component({
  selector: 'app-demo',
  standalone: true,
  imports: [ChartModule], // ⬅️ Inclúyelo en los imports del componente standalone
  templateUrl: './demo.component.html',
  styleUrls: ['./demo.component.css']
})
// src/app/chart-demo/chart-demo.component.ts

// ... (imports y @Component)

export class DemoComponent implements OnInit {
    data: any;
    options: any;

    ngOnInit() {
        const documentStyle = getComputedStyle(document.documentElement);
        // Colores base para la gráfica
        const primaryColor = documentStyle.getPropertyValue('--blue-500');
        const secondaryColor = documentStyle.getPropertyValue('--yellow-500');
        const tertiaryColor = documentStyle.getPropertyValue('--green-500');
        const textColor = documentStyle.getPropertyValue('--text-color');

        // 1. **Datos del Gráfico (data):**
        this.data = {
            labels: ['Tecnología', 'Comida', 'Hogar'], // Etiquetas para cada porción
            datasets: [
                {
                    data: [300, 50, 100], // Los valores de cada porción
                    backgroundColor: [
                        primaryColor,
                        secondaryColor,
                        tertiaryColor
                    ],
                    hoverBackgroundColor: [
                        documentStyle.getPropertyValue('--blue-400'),
                        documentStyle.getPropertyValue('--yellow-400'),
                        documentStyle.getPropertyValue('--green-400')
                    ]
                }
            ]
        };

        // 2. **Opciones del Gráfico (options):**
        this.options = {
            cutout: '60%', // Este valor define el tamaño del hueco central (para Doughnut)
            plugins: {
                legend: {
                    labels: {
                        usePointStyle: true,
                        color: textColor
                    },
                    position: 'bottom' // Puedes mover la leyenda abajo
                }
            }
        };
    }
}